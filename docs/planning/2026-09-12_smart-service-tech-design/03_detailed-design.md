# 第三步：详细设计

每个模块按「输入 / 输出 / 实现要点 / 降级」描述。所有 LLM 输出均要求 JSON Schema 约束并做校验，校验失败重试一次后走降级。

本文的接口与事件定义以 08_session-execution-contract.md 为准；规则检查点、产品适用性、排障计划、知识状态与凭证规则以 09_plans-rules-knowledge.md 为准。下文只保留模块级要点并指向这两份。

## 1. 模块设计

### 1.1 情绪识别（emotion）
- 输入：当前用户消息、上一轮情绪。
- 输出：`{level: calm|anxious|angry, strategy: normal|reassure_first|reassure_and_shorten}`。
- 要点：走 ModelRouter 的 intake 任务（轻量档模型）；strategy 注入系统提示，控制开场安抚句与步骤长度（angry 时每步不超过两句）。
- 降级：失败视为 calm。

### 1.2 意图与线索抽取（intake）
- 输入：用户文本、是否有图片。
- 输出：`{product_hints: [..], symptoms: [..], wants_human: bool}`。
- 要点：进入 LLM 之前先过 CP-in 规则检查（安全词字典、请求人工），命中 R3 / R4 直接 escalate（09 §1）；随后抽取型号、品类词、症状词。此调用 tag=internal，输出不进聊天流；安抚句由 reply.stream（tag=user_visible）单独生成。
- 降级：抽取为空时进入 disambiguate 并向用户提问品类。

### 1.3 产品消歧（disambiguate）
- 输入：product_hints。
- 输出：product_candidates 或 product_confirmed。
- 输出补充：product_state ∈ {confirmed_sku, category_only, unknown}（09 §2.1）。
- 要点：规则服务在 PostgreSQL 产品目录上做型号精确 + 别名模糊匹配；多命中 → prepare_card → await_input 等待卡片选择；候选带 in_scope 标记；零命中 → 追问品类。不使用 LLM 猜测型号。
- 降级：用户两次未选中：有扫地机品类线索 → category_only，仅允许 category_generic 知识；否则 escalate(R7 品类不明)。不再降级为「通用扫地机」。选中 in_scope=false → out_of_scope 子流程。

### 1.4 故障定位（diagnose）
- 输入：product_confirmed、symptoms、图片。
- 输出：hypotheses、image_observations、retrieval_trace。
- 流程：
  1. 有图时调 ModelRouter diagnose.vision（视觉模型）输出 `{observations: [..], visible_parts: [..]}`。
  2. 文本 query（症状 + 型号）先发检索，与读图并行；观察结果过 CP-in，若带来新信息再补一次检索。检索传 KnowledgeScope，适配器映射为 WeKnora 允许的 knowledge_ids，允许集合为空直接 no_match（09 §2.3）。工单 result≠solved 的只作反证。
  3. 调 diagnose.synthesize（强推理模型，tag=internal）汇总为 plans_ranked `[{plan_id, confidence 0-1, evidence_ids}]`，plan_id 限定为当前允许集合内的预写计划枚举，最多 3 个。
- 降级：ToolResult 四态 ok / no_match / unavailable / replay（09 §4）。no_match 与 unavailable 时若存在 applies_to 匹配的预写计划则按计划默认顺序执行并标注来源，否则 escalate(R5)。不允许 LLM 用常识生成假设。

### 1.5 排障引导（guide）
- 输入：plan_cursor 指向的计划步骤（instruction_src 原文、expected_result、caution）、emotion.strategy、product_confirmed。
- 输出：`step: {step_id, plan_id, plan_version, step_no, title, instruction, expected_result, caution?, evidence_ids}`。
- 要点：三段式 prepare_card → CP-pre-step → await_input（08 §3）。LLM 只把 instruction_src 改写成用户可执行的一句话，不得增删动作；evidence_ids 必须全部在当前允许集合内，否则丢弃该步骤取下一步。card_id 由 (session_id, plan_id, step_id) 派生，重跑稳定。
- 降级：改写失败 → 直接使用 instruction_src 原文。

### 1.6 结果确认（verify）
- 输入：step_feedback 动作（action_id、interrupt_id、card_id、expected_version、feedback、note?）。
- 逻辑：apply_action 去重与版本校验（08 §4）→ 写 steps_executed → 更新 counters（solved 结束；not_solved executed+1；cannot_do skipped+1）→ 按 plan.next_on[feedback] 推进 plan_cursor，EXHAUSTED 时按 09 §3.4 切换计划 → CP-verify 判定 R1 / R1b / R1c / R2。
- 无 LLM 参与。

### 1.7 升级判定与摘要（escalate）
- 规则表（规则服务，配置化，带编号）：

| 规则 | 条件 | 说明 |
| --- | --- | --- |
| R1 | counters.executed ≥ 4 | 步数上限（CP-verify） |
| R1b | counters.skipped ≥ 3 | 用户连续无法操作（CP-verify） |
| R1c | executed + skipped ≥ 6 | 硬上限（CP-verify） |
| R2 | 当前计划 EXHAUSTED 且无 confidence ≥ 0.3 的下一计划 | 计划耗尽（CP-verify） |
| R3 | request_human 动作或文本明确要求人工 | 任何时刻（CP-in） |
| R4 | 安全词字典命中：文本、图片观察、动作备注 | 立即升级，优先于一切排障与凭证收集（CP-in / CP-pre-step） |
| R5 | diagnose 无可用计划 | 无知识可用 |
| R6 | 用户提及退换 / 保修 | 常规升级时进入凭证子流程 |
| R7 | product_state=unknown 且追问 2 次 | 品类不明 |
| R8 | 选中 in_scope=false 产品 | 范围外产品 |

- 子流程：安全升级（R4）或 request_human → 直接 summarize，receipt.status=not_collected，摘要后可选补凭证；常规升级 → collect_receipt → extract → confirm_fields → lookup → summarize（09 §5.1）。
- 摘要结构 `summary` 字段见 08 §5；LLM 只做字段内文本润色（tag=internal），模型不可用时直接渲染结构字段，不阻断交接。

### 1.8 购买凭证识别与渠道判断（warranty）
- 输入：purpose=receipt 的图片，或用户手输的订单号 / 渠道文本。
- 流程：collect_receipt（awaiting_input=upload_receipt，可 skip_receipt）→ extract：warranty.receipt_ocr 输出 `{fields, confidence per field, unreadable[]}` → confirm_fields：receipt_card + awaiting_input=confirm_receipt，用户确认或修改（edited[] 记录）→ lookup：09 §5.2 规则 L1–L6，核对 `order.sku == product_confirmed.sku`，保留订单实际 channel / date，低置信未修改字段命中订单降为 needs_manual_check → 输出 `receipt: {status, verified_facts, conflicts, next_step}`。
- 要点：LLM 只抽取字段；订单归属、渠道与下一步全部由规则决定；**不输出质保资格结论**，只输出已核实事实与下一步。
- 降级：识别失败或 unreadable 全字段 → 让用户手输或 skip；skip → status=not_collected。

## 2. 接口设计

### 2.1 HTTP
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /sessions | 新建会话，返回 session_id、version |
| POST | /sessions/{id}/messages | 文本 + 可选图片（multipart，字段 purpose=fault / receipt），返回 SSE 流；guide / verify 阶段等价于 rediagnose |
| POST | /sessions/{id}/actions | 动作：select_product、step_feedback、confirm_receipt、skip_receipt、request_human、rediagnose；载荷与校验见 08 §4 |
| POST | /sessions/{id}/cancel | 取消 active run（08 §7） |
| GET | /sessions/{id} | 权威快照（08 §6） |
| GET | /sessions/{id}/runs/{run_id}/events?after_seq= | 续接事件流：先重放 session_events 再接实时 |
| GET | /health | 组件健康：models（按 lane）、weknora、db、redis |

### 2.2 SSE 事件
事件、动作、快照三套 Schema 的唯一定义在 08 §4–§6，此处不重复。关键约束：`step_card.step` 与 `escalation_summary.summary` 为对象层级；`evidence.items[].evidence_id` 稳定并被 `step.evidence_ids` 引用；`message` 只来自 tag=user_visible 的调用；每个 run 以 `done` 结束。

### 2.3 与 WeKnora 的适配器接口
```
class KnowledgeAdapter(Protocol):
    def hybrid_search(kb: str, query: str, top_k: int, allow: KnowledgeScope) -> ToolResult[list[Hit]]

KnowledgeScope = {product_state, sku?, category}
ToolResult.status ∈ {ok, no_match, unavailable, replay}，附模型可读 hint；单次返回 ≤ 2k token（07 §14）
Hit = {evidence_id, knowledge_id, chunk_id, doc_version, snippet, score, counter_evidence: bool}
```
实现一：WeKnoraHTTPAdapter，调用官方 knowledge-search / hybrid-search HTTP 接口，scope → knowledge_ids 映射见 09 §2.3；集成验证项 IV-1：锁定镜像版本后核对参数名与过滤语义，不支持则后过滤。实现二：ReplayKnowledgeAdapter，仅在 REPLAY_CASE_ID 设置时启用，未命中返回 unavailable。不再有「MockAdapter 兜底真实故障」。

### 2.4 模型适配器接口（ModelRouter）
```
class ModelRouter(Protocol):
    async def invoke(task: str, messages: list[Message], schema: type[BaseModel], *, budget_ms: int) -> ModelResult[T]
        # 结构化调用：返回 parsed 与 model_used / lane / attempts；tag=internal
    def stream(task: str, messages: list[Message], *, budget_ms: int, message_id: str) -> AsyncIterator[StreamEvent]
        # 文本流：产出 delta / aborted / switched(model_tier) / end；tag=user_visible
```
- 两个入口分开：结构化输出用 invoke，用户可见文本用 stream。stream 中主模型中断时产出 `aborted`，随后由 API 层发 message_end(aborted) 与新的 message_start(replaces)。
- budget_ms 由节点按 08 §8 计算传入；ModelRouter 是唯一重试层，厂商 SDK max_retries=0。
- 节点只传 task 名（intake、diagnose.vision、diagnose.synthesize、guide.step、reply.stream、escalate.summary 等），模型选择、降级链、参数映射全部由 config/models.yaml 决定。
- 底层用 LangChain init_chat_model 建实例；结构化输出按模型能力选 json_schema / json_object / 工具调用三种方法，统一 Pydantic 校验。
- ModelResult 带 model_used、lane、attempts，写入会话状态与 Langfuse。
- 回放模式实现 ReplayRouter，按 case_id + 版本清单命中录制包（09 §6）；非回放的响应缓存键为 sha256(task, prompt_ver, schema_ver, model_id, input_text, image_sha256s, kb_ver)。
- 详细路由表、能力矩阵、降级规则见 model-selection.md 第 3 节。

## 3. 数据设计

### 3.1 PostgreSQL
- products(sku, name, aliases[], category, image_url)
- sku_fault_cards(sku, card_text, doc_version, updated_at) — 预拼装故障卡，约 800 token，产品确认后预加载进上下文（07 §7）
- dealers(name, region, authorized bool, warranty_note)
- orders_mock(order_no, sku, channel, purchase_date)
- plans(plan_id, version, fault, applies_to jsonb, steps jsonb) — 预写排障计划（09 §3）
- session_events(session_id, seq, run_id, event_json, created_at) — 事件日志，timeline 与续接来源
- session_actions(session_id, action_id, result_json, created_at) — 动作幂等
- session_images(image_id, session_id, purpose, sha256, bytes, created_at) — 图片，1 小时清理
- sessions(session_id, version, stage, active_run_id, pending_input_json, updated_at) — 只读投影，可重建
- langgraph_checkpoints（框架自带，权威业务状态）

### 3.2 WeKnora 知识库
- kb_manual：说明书 PDF、FAQ Markdown、排障手册；元数据 {scope: sku / category_generic, sku_list, category, doc_version}。
- kb_tickets：历史工单 CSV，每行一条，字段 {sku, symptom, root_cause, steps, result}；元数据 {scope, sku_list, category, result, doc_version}。result≠solved 只作反证。
- 分块：父子分块，父块 800 字，子块 200 字；检索开 BM25 + 向量，图谱路径演示阶段关闭。

## 4. Prompt 设计要点
- 系统提示分三层：角色与安全边界（固定）、情绪策略（每轮注入）、状态摘要（每轮注入）。
- 所有生成节点给 JSON Schema 与一个示例。
- 排障步骤 Prompt 只允许改写给定 instruction_src，输出的 evidence_ids 由规则填入而非模型生成。
- 所有外部文本（用户输入、OCR、检索片段）包在 `<data>` 段，系统提示声明其非指令（07 §15）。
- Prompt 文件化到 prompts/ 目录，带版本号，见第四步。

## 5. 前端组件
详见 05_frontend-design.md。要点：Vite + React 19 + TypeScript；SSE 事件用判别联合类型镜像后端 Pydantic 模型并由 zod 校验；卡片为预注册固定组件，模型只决定发哪种卡与字段；前端 6 态 ui 状态机由 reducer 驱动。

## 6. 后端流式实现要点
- FastAPI `StreamingResponse(media_type="text/event-stream")`，响应头加 `X-Accel-Buffering: no`；每 5 s 发 ping。
- LangGraph `graph.astream(input, config, stream_mode=["updates", "custom", "messages"])`：
  - `messages` 只透传 metadata.tags 含 `user_visible` 的调用（按 LangGraph 官方 tags / langgraph_node 过滤），映射为 message_start / message / message_end；其余调用的 token 丢弃。
  - `custom`（节点内 `get_stream_writer()`）→ progress / tool_call / 卡片 / evidence / awaiting_input。
  - `updates` → 状态迁移日志与 version 递增。
- 每条事件先写 session_events 再发送，seq 单调递增；流末尾必发 done，异常路径 error → done(error)。
- 等待输入用 prepare_card → await_input(interrupt) → apply_action 三段式（08 §3）；/actions 以 `Command(resume=action)` 恢复并开新 SSE 流；同会话加锁串行。
- 契约生成：`make contracts` 从 Pydantic 模型生成 JSON Schema 与前端 TS 类型，CI 比对（08 §9）。
