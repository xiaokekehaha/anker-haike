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
- 输入：用户文本、是否有图片、当前状态摘要（已确认产品、有效症状、最近步骤及反馈；只取相关上下文）。
- 输出：`{product_hints: [..], symptoms: [..], wants_human: bool}`。
- 要点：进入 LLM 之前先过 CP-in 规则检查（安全词字典、请求人工），命中 R3 / R4 直接 escalate（09 §1）；随后一次调用合并情绪与产品 / 症状抽取。意图处理以规则、动作 kind 与 stage 为准，模型补充 wants_human 等语义线索，不新增通用 intent 枚举或分类调用。此调用 tag=internal，输出不进聊天流；安抚句由 reply.stream（tag=user_visible）单独生成。
- 多轮：复用同一抽取函数；symptoms 表示结合本轮补充 / 否定后的有效症状，事实只能来自用户描述与已有上下文。产品线索仍交 disambiguate 确认，不能由模型直接写成 confirmed_sku。更新与查询边界见 §1.4.1。
- 上述输出是消费后的业务字段；原始增量抽取与合并遵循[连续追问设计 §3](../2026-09-12_conversation-memory-design/architecture-requirements.md#3-每条追问的处理链路)：未提及保持、明确纠正才替换，不能把一次空抽取当作撤销全部。`needs_clarification` 等模型线索须经过后端检查。
- 降级：首次抽取为空且品类未知时进入 disambiguate 追问；已有产品上下文时不因抽取失败清空确认结果，查询回退见 §1.4.1。

路由只需三种处理结果：必要信息足够且符合当前状态 → 继续；缺失 / 冲突 / 指代不明 → 澄清；人工请求、安全风险或两次澄清后仍不明 → 升级。由后端根据状态与规则决定，不以模型自报置信度代替检查。次数、纠错与退出以 09 §1.1 为准；按钮动作的 422 / 409 与映射验收以 08 §4 为准。

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
  2. 按 §1.4.1 规范化文本 query（有效症状 + 已确认产品 / 品类）先发检索，与读图并行；补检索名额由图片新增信息或 §1.4.2 的无命中改写共享，每 run 最多两轮。检索传 KnowledgeScope，适配器映射为 WeKnora 允许的 knowledge_ids，允许集合为空直接 no_match（09 §2.3）。工单 result≠solved 的只作反证。
  3. 调 diagnose.synthesize（强推理模型，tag=internal）汇总为 plans_ranked `[{plan_id, confidence 0-1, evidence_ids}]`，plan_id 限定为当前允许集合内的预写计划枚举，最多 3 个。
- 降级：ToolResult 四态 ok / no_match / unavailable / replay（09 §4）。真实 no_match 可按 §1.4.2 尝试一次受控改写；不满足条件、补救失败或 unavailable 时，有适用预写计划则按默认顺序执行并标注来源，否则 escalate(R5)。不允许 LLM 用常识生成假设。

#### 1.4.1 理解、查询与召回的最小契约

本节补齐已有模块之间的行为约定，由票 32 / 37 实现；不表示当前代码已经全部满足。

| 环节 | 归属与最小实现 | 输出 / 下一步 |
| --- | --- | --- |
| 意图与上下文 | CP-in 优先；卡片动作按 kind + stage 路由；自由文本复用一次 intake 抽取 | 产品线索、有效症状、情绪、wants_human；产品消歧或升级 |
| 查询规范化 | diagnose 内现有 `retrieval_query(state) -> str` 纯函数 | 一个 query；没有独立改写模型调用 |
| 无命中补救（可选） | diagnose 内经 ModelRouter 调用 `query.rewrite`，默认关闭 | 一个受校验的查询，仍在相同 scope 内补检索；见 §1.4.2 |
| 召回与重排 | KnowledgeAdapter 限定 scope，WeKnora 执行混合检索与已有重排 | 四态 ToolResult 与带来源的 hits |
| 计划与话术 | diagnose.synthesize 选允许计划；guide.step 改写 instruction_src，规则校验 | plans_ranked、可执行步骤文字 |
| 展示 | 后端根据状态、规则与经校验结果发送 08 的现有事件 | 五种固定卡片；模型不决定组件、布局或按钮动作 |

查询规范化规则：

1. `confirmed_sku` 只取已确认产品名 / 型号；`category_only` 只取已确认品类，不拼候选型号；`unknown` 留在消歧阶段，不发检索。scope 始终由状态构造，query 不能扩大范围。
2. 将产品信息与有效 symptoms 按固定顺序拼接，去重、清理空白。保留否定、部件与错误码，不猜型号、故障原因或用户没有说过的限制。近期步骤 / 反馈供理解与计划筛选，不把整段历史塞入 query。
3. 抽取失败或 symptoms 为空时，使用已确认产品 / 品类 + 当前用户原文回退。原文也为空且没有新图片时，询问具体故障；仅图片输入按既有读图路径处理。纠正内容无法可靠理解时先澄清，不沿用被否定事实下发新步骤。
4. 首轮形成一个文本 query，分别用于说明书与工单库（两库并发）。至多再补一轮：优先采用及时返回的新图片观察，否则在真实无命中且开关开启时采用 §1.4.2 的模型改写。两种补救共享名额，不叠加成三轮；不增加额外重试层。**（D19 修订）** 允许基于 `retrieval.yaml` 已审核同义表的**确定性**多查询扩展（不调模型、变体数与请求数有上限），同库多变体按 RRF 合并、跨库按库内名次交错；允许对合并结果做一次可选重排（`rerank.enabled`，默认关，WeKnora 的 hybrid-search 本身不重排）。不引入模型生成的多查询。
5. 沿用 `retrieval_trace` 记录实际 query、scope、status、hit_ids、scores，并关联当前 session/run；用户原文保留在已有消息记录。query 是内部调试数据，不新增 SSE 事件或卡片；`tool_call` 只展示简短阶段说明。

多轮更新规则：

- 「还是不吸」继承已确认产品与未解决症状；「还有异响」补充现象；「不是吸力小，是有异响」替换被否定的有效症状，原话仍保留在消息记录中。
- rediagnose 复用 intake（含情绪抽取），然后重新构造 query；保留 steps_executed 与 counters，已执行的步骤不会因重新诊断而被当成未执行。
- 用户明确纠正型号时回到现有 disambiguate；重新确认前不继续使用旧 SKU 生成步骤，歧义时不扩大检索范围。新计划的证据必须按新 scope 校验，旧证据可供历史展示，不作为新步骤的默认依据。
- `step_feedback` 按现有规则推进；`request_human` / R3 / R4 走升级；凭证输入走既有凭证子流程。这些路径无需先执行知识召回。

默认查询使用以上规范化；额外模型改写作为默认关闭的增强，规则见下节。「文字润色」仍是 guide.step / reply.stream / escalate.summary 的职责。

#### 1.4.2 无命中时的一次查询改写（默认关闭）

编排开关 `config/retrieval.yaml: query_rewrite.enabled=false`（待票 32 实现）。调用入口复用 `ModelRouter.invoke(task="query.rewrite", ..., budget_ms=...)`，路由注册见 model-selection §3.7.1，tag=internal。该调用只改检索表达，不联网搜索，也不产生新的业务事实。

```text
首轮实际检索 no_match + 开关开启 + 有剩余名额与预算
→ ModelRouter 返回一个 query → 后端校验
→ 同一产品范围再检索一轮
→ 有适用证据：选择允许计划 → 组织步骤文字 → 校验并发卡
→ 仍无结果 / 改写失败：适用预写计划，或升级 R5
```

- **触发：** 用户信息已足够，scope 有至少一份允许文档；首轮实际请求的库全部正常返回 no_match。允许集合为空、任一请求 unavailable、已有可用 hits、处于澄清 / 回放 / 取消状态均不触发。读取每库状态与允许集合判定，不只看汇总状态。完整决策表见 09 §4.1。
- **输入 / 输出：** 用户原话、已确认产品 / 品类、有效症状、首次 query；提示限定保留原意与否定，不猜型号、部件、故障原因或维修动作，只输出 `{"query": "..."}`。Schema 仅允许 query，一个非空字符串，去空白后最多 200 字符，禁止附带 scope / SKU 过滤字段。
- **保守校验：** 空值、格式错误、与首次 query 规范化后相同则放弃；检查型号、错误码、数值与否定是否被更改，拒绝新增未经输入支持的部件、原因或操作。同义表达通过少量已审核术语映射放行；无法确定是否改变原意时弃用，不另加模型裁判。Schema 校验不能证明语义等价，启用前必须用人工标注样例验证。
  - 实现口径（2026-09-13 修订）：部件用 `PARTS` 清单判定、原因 / 操作用 `FORBIDDEN_NEW`；否定分方向——凭空**加**否定必拒，**丢**否定只在被否定的是真事实时拒（「不是 X，是 Y」纠正句式里的否定属于被纠正掉的旧事实，比较前剥离）；另加漂移锚点检查，改写须保留原症状的一个 2 字词或一个已审核同义词。早期「整句须能由原文切出」的严格模式保留在 `query_rewrite.strict_terms`（默认 false），实测会拒掉几乎所有自然改写。
- **例子：** 已确认扫地机，原话「它跑完了，地上还是一堆渣」可映射到「扫地机器人 清扫后残留碎屑 清洁效果差」；不能增写「电机损坏」或另一个型号。产品过滤始终取后端原 scope；改写只影响匹配文本，不写回 symptoms 或产品状态。
- **次数 / 预算：** 每 run 至多一次 rewrite invoke、至多两轮检索（每轮对允许的各库最多一次请求）。与图片补检索共享名额，图片有新增信息时优先；补检索一旦启动，晚到图片仍过 CP-in，但不再触发第三轮。剩余时间与取消检查、3 s + 3 s 补救上限见 08 §8；Router 内部尝试共用这 3 s，节点不重新 invoke。
- **结果 / 追踪：** 经校验的新 query 仍交原 KnowledgeAdapter，适用性、来源和计划枚举校验照常；失败走 09 §4，不递归改写。沿用模型 / 检索 trace，额外记 `rewrite_triggered`、跳过 / 拒绝原因、前后 query、每库状态、检索轮次及额外耗时（内部日志，不扩展前端事件）。
- **启用门槛：** 以人工标注的口语漏召回样例对比关闭 / 开启，检查新增适用证据、错误匹配、语义漂移与端到端延迟；确认有收益后才启用。关闭开关即可恢复默认链路。

#### 1.4.3 命中相关性评分（retrieve.grade，默认关闭）

开关 `config/retrieval.yaml: grade.enabled=false`（D19）。首轮命中后一次轻量结构化调用，任务名 `retrieve.grade`，只回答两个问题：每条命中是否与本次故障相关（relevant / irrelevant / unsure），以及整体 coverage（sufficient / insufficient / none）。

- **它不是证据**：评分结果不进 `evidence` 事件、不进快照、不进卡片，也不改 `knowledge_status`；被判 irrelevant 的命中仍作为「检索到的来源」发给前端，只是不进 synthesize 的输入。
- **只做减法**：只剔除 irrelevant，且至少保留 `keep_min` 条原始分最高的命中（标 `kept_min`）；反证工单不因评分升格。
- **校验在代码侧**：`evidence_id` 必须在输入集合内，缺失补 unsure，coverage 非法回退 insufficient，声称 sufficient 却无一条 relevant 时降级为 insufficient（国产链只有 json_object，枚举不可依赖）。
- **失败不阻断**：模型超时 / 不可用 / 容量拒绝一律记 `ungraded`，不过滤、不升级，主流程照常。
- **对补检索的影响**：graded 且无一条 relevant 时，把该库的 ok 视作 no_match 参与 09 §4.1 的改写决策（只影响是否补一轮，不改写给前端的知识状态）。第二轮新增命中默认标 unsure；`grade.second_round` 开启才做第二次评分（子流程模型调用上限仍为 4）。
- **启用门槛**：与 §1.4.2 同，须用人工标注样例对照关闭 / 开启，确认剔除的确实是无关命中、且没有把应采信的段落误剔。

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
| R7 | 连续澄清 2 次并收到回答后，必要信息仍不明或冲突 | reason=product / symptom / conflict；见 09 §1.1，保留原品类不明场景 |
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
详见 05_frontend-design.md。要点：Vite + React 19 + TypeScript；SSE 事件用判别联合类型镜像后端 Pydantic 模型并由 zod 校验；卡片为预注册固定组件，由后端状态机与规则决定种类和动作，模型只提供经校验的文字 / 结构化字段；前端 6 态 ui 状态机由 reducer 驱动。

## 6. 后端流式实现要点
- FastAPI `StreamingResponse(media_type="text/event-stream")`，响应头加 `X-Accel-Buffering: no`；每 5 s 发 ping。
- LangGraph `graph.astream(input, config, stream_mode=["updates", "custom", "messages"])`：
  - `messages` 只透传 metadata.tags 含 `user_visible` 的调用（按 LangGraph 官方 tags / langgraph_node 过滤），映射为 message_start / message / message_end；其余调用的 token 丢弃。
  - `custom`（节点内 `get_stream_writer()`）→ progress / tool_call / 卡片 / evidence / awaiting_input。
  - `updates` → 状态迁移日志与 version 递增。
- 每条事件先写 session_events 再发送，seq 单调递增；流末尾必发 done，异常路径 error → done(error)。
- 等待输入用 prepare_card → await_input(interrupt) → apply_action 三段式（08 §3）；/actions 以 `Command(resume=action)` 恢复并开新 SSE 流；同会话加锁串行。
- 契约生成：`make contracts` 从 Pydantic 模型生成 JSON Schema 与前端 TS 类型，CI 比对（08 §9）。
