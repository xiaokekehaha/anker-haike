# 会话执行契约（run / interrupt / card / action / snapshot）

整理日期：2026-09-12。响应评审 R4、R5、R6、R9。本文是前后端、模型层、运维文档共同引用的唯一契约来源；03 / 05 中的接口描述以本文为准，冲突时改那两份。

## 1. 术语

| 术语 | 定义 |
| --- | --- |
| session | 一次用户服务过程，`session_id` 标识；一个 session 同一时刻最多一个 active run |
| run | 一次图执行，从收到消息或动作开始，到 `done` 结束；`run_id` 标识 |
| version | session 的单调递增整数，每次状态提交（checkpoint 写入）加一；动作必须带 `expected_version` |
| card | 需要用户响应的界面对象（产品确认、排障步骤、凭证确认、摘要）；`card_id` 稳定，卡片内容在持久化后不再变化 |
| pending_input | 当前唯一允许的用户输入类型与其绑定的卡片；不存在时 Composer 处于自由输入 |
| interrupt | LangGraph 中断点；`interrupt_id = card_id`，一一对应 |
| action | 用户对卡片的响应或全局请求；带 `action_id` 幂等键 |
| snapshot | `GET /sessions/{id}` 返回的权威视图，用于恢复 |

## 2. 权威状态与投影

- **权威来源**：LangGraph checkpoint（PostgresSaver）。业务状态全部在图状态里。
- **事件日志**：`session_events(session_id, seq, run_id, event_json, created_at)` 追加写，每条发往前端的事件同时落库。timeline 由它重建，不由前端缓存。
- **投影表**：`sessions(session_id, version, stage, active_run_id, pending_input_json, updated_at)` 是从 checkpoint 与事件日志派生的只读投影，允许丢失后重建；任何业务逻辑不得只读它。
- **动作去重表**：`session_actions(session_id, action_id, result_json, created_at)`，主键 `(session_id, action_id)`。

## 3. 图节点拆分（应对 interrupt 重跑语义）

LangGraph 恢复时会从包含 `interrupt()` 的节点开头重跑，节点内 interrupt 之前的代码会再次执行。因此：

```
prepare_card ──▶ await_input ──▶ apply_action ──▶ (下一业务节点)
 生成并持久化       只读 pending_card     校验动作、去重、
 pending_card       发卡片事件、interrupt   写入结果
```

- `prepare_card`：调用模型或规则生成卡片内容，写入状态 `pending_card = {card_id, kind, payload, version}`，`card_id = uuid5(session_id, stage, plan_cursor 或 candidate_hash)`，保证同一业务位置重跑得到同一 id。此节点不含 interrupt，只执行一次。
- `await_input`：从状态读取 `pending_card`，发卡片事件与 `awaiting_input`，随后 `interrupt()`。重跑时重复发送同一卡片事件，前端按 `card_id` 幂等（已存在则更新而非追加）。
- `apply_action`：接收 `Command(resume=action)`，校验后写入 `steps_executed` 等业务字段，清空 `pending_card`。副作用（调用规则、记账）都在此节点且以 `action_id` 幂等。

## 4. 动作协议

`POST /sessions/{id}/actions`

```json
{
  "action_id": "uuid（前端生成，重试时复用）",
  "interrupt_id": "与 awaiting_input.interrupt_id 相同",
  "card_id": "与目标卡片相同",
  "expected_version": 17,
  "kind": "select_product | step_feedback | confirm_receipt | skip_receipt | request_human | rediagnose",
  "payload": { }
}
```

| kind | payload | 允许时机 |
| --- | --- | --- |
| select_product | `{sku}` | pending_input.kind = select_product |
| step_feedback | `{feedback: solved / not_solved / cannot_do, note?}` | pending_input.kind = step_feedback |
| confirm_receipt | `{fields: {order_no?, channel?, purchase_date?}, edited: [field...]}` | pending_input.kind = confirm_receipt |
| skip_receipt | `{reason: none / unreadable / later}` | pending_input.kind ∈ {upload_receipt, confirm_receipt} |
| request_human | `{}` | 任何时刻，包括 awaiting_input 与 streaming |
| rediagnose | `{text?, image_ids?}` | stage ∈ {guide, verify} 且无 active run；用于用户补充新症状、照片或纠正 |

服务端处理顺序：

1. 取 session 级锁（PostgreSQL advisory lock 或 Redis lock，超时 30 s）。同会话串行。
2. 查 `session_actions`，`action_id` 已存在 → 直接返回已记录结果并重放对应事件流（状态 200，`replayed=true`）。
3. 校验：`expected_version == 当前 version`，否则 409 并附最新 snapshot；`interrupt_id/card_id` 等于当前 pending_input，否则 409 `stale_card`；`kind` 在允许时机内，否则 409 `not_allowed_now`。
4. `request_human` 例外：忽略 version 与 pending 校验，若有 active run 先取消再执行。
5. 写 `session_actions` 占位 → 执行 `Command(resume=...)` → 开 SSE 流 → 完成后回填结果。

动作失败边界：未知 kind / 不合法 payload 在 Schema 校验层返回 422，不调用模型猜动作；已知动作但阶段不允许、版本过期、卡片过期返回对应 409 与最新快照。拒绝请求不得推进游标、增加业务计数或启动错误分支。合法 `step_feedback(not_solved)` 必须进入 verify，`request_human` 必须进入 escalate；用路由表与端到端测试覆盖，模型不参与按钮路由。自由文本的不确定、澄清和纠正按 09 §1.1；不能把语义不明伪装成动作成功。

## 5. 事件协议（唯一定义）

所有事件 JSON 带 `type`、`seq`（会话内单调递增）、`run_id`。

| type | 载荷 | 说明 |
| --- | --- | --- |
| run_started | `{resumed: bool, deadline_ms}` | deadline 为本 run 故障时的最大总时长，前端硬上限 = deadline + 5 s |
| ping | `{}` | 心跳，每 5 s；只维持连接，不延长 deadline |
| progress | `{stage, substage?}` | substage 用于 escalate 子流程 |
| tool_call | `{tool_id, name, status: started / finished / failed, summary?}` | |
| message_start | `{message_id, replaces?: message_id}` | 开始一段面向用户的文本；`replaces` 表示替换先前中断的消息 |
| message | `{message_id, delta}` | 只来自标记 `user_visible` 的 reply.stream 调用 |
| message_end | `{message_id, status: completed / aborted, model_tier?: primary / fallback}` | aborted 后若继续回答，必须新开 message_start 并 replaces |
| product_card | `{card_id, version, candidates: [{sku, name, category, image, in_scope: bool}]}` | in_scope=false 的候选选中后进入范围外处理 |
| step_card | `{card_id, version, step: {step_id, plan_id, plan_version, step_no, title, instruction, expected_result, caution?, evidence_ids: []}}` | 唯一层级：`step` 对象 |
| evidence | `{items: [{evidence_id, source, doc_id, doc_version, chunk_id, snippet, score, status: ok / replay}]}` | evidence_id 稳定，供 step.evidence_ids 引用 |
| receipt_card | `{card_id, version, fields: {order_no?, channel?, purchase_date?, amount?}, confidence: {field: 0-1}, unreadable: [field]}` | 不含质保结论 |
| awaiting_input | `{kind: select_product / step_feedback / upload_receipt / confirm_receipt, interrupt_id, card_id, version}` | 与 pending_input 同结构 |
| escalation_summary | `{card_id, summary: {product, problem, observations, hypotheses, steps: [{step_id, title, feedback}], reason: {rule_id, text}, emotion, receipt: {status, verified_facts, conflicts, next_step}, model_trace}}` | 唯一层级：`summary` 对象 |
| error | `{code, message, recoverable, retry_with_same_action: bool}` | recoverable 且 retry_with_same_action 时前端复用 action_id 重试 |
| done | `{reason: completed / awaiting_input / error / cancelled, version}` | 流终止；version 为本 run 结束后的会话版本 |

约束：

- `messages` 流模式只透传带 tag `user_visible` 的模型调用；内部结构化调用一律 `invoke` 且 tag `internal`，其 token 不进入任何事件。校验失败与重试对用户不可见。
- 流式主模型中途失败：发 `message_end(status=aborted)`，降级模型从头生成并以 `message_start(replaces=旧 id)` 开始；前端替换而非拼接。
- 每个 run 必以 `done` 结束；异常路径为 `error` → `done(reason=error)`。

## 6. 快照协议

`GET /sessions/{id}` →

```json
{
  "session_id": "...",
  "version": 17,
  "stage": "guide",
  "substage": null,
  "active_run": { "run_id": "...", "started_at": "...", "deadline_at": "..." } | null,
  "pending_input": { "kind": "step_feedback", "interrupt_id": "...", "card_id": "...", "version": 17 } | null,
  "timeline": [ 事件日志按 seq 重放后的折叠视图：消息（完整文本）、卡片（含用户已选结果）、工具行 ],
  "last_error": { "code": "...", "at": "..." } | null,
  "cancelled_run": { "run_id": "...", "at": "..." } | null
}
```

前端恢复规则：

1. 页面加载或断流后**先读 snapshot**。
2. `active_run` 非空且未过 deadline → 进入 streaming 态，调用 `GET /sessions/{id}/runs/{run_id}/events?after_seq=N` 续接事件流（服务端从 session_events 重放后接实时）。
3. `active_run` 为空且 `pending_input` 非空 → awaiting_input 态，卡片按 timeline 中的 card_id 置为待反馈。
4. 两者皆空 → idle。
5. 前端本地状态与 snapshot 冲突时以 snapshot 为准。

## 7. 取消

- `POST /sessions/{id}/cancel {run_id}`：服务端设置取消标志，图在下一个节点边界停止，写 `done(reason=cancelled)` 并持久化 `cancelled_run`。
- 前端 abort fetch 不等于取消；断开连接后 run 继续到 deadline 或完成，结果可通过 snapshot 读到。
- 取消后 pending_input 保持取消前的值（若有），用户可继续。

## 8. 截止时间与重试责任

| 项 | 值 |
| --- | --- |
| 正常目标（测量口径） | 首个 message delta ≤ 2 s；步骤卡就绪：文本轮 ≤ 8 s，含图轮 ≤ 15 s。分别记录 `first_visible_ms`、`card_ready_ms` |
| run deadline（故障最大等待） | 文本轮 25 s，含图轮 40 s，凭证轮 30 s |
| task 预算 | `min(task 默认超时, run 剩余时间 − 2 s)`；剩余不足 3 s 时跳过可选 task（如第二次检索、摘要润色） |
| 唯一重试层 | ModelRouter。厂商 SDK `max_retries=0`；节点不重试；HTTP 层不重试 |
| ModelRouter 重试预算 | 同模型最多 1 次，链上最多 3 家，且总耗时不超过 task 预算 |
| 可选查询改写 | 默认关闭；触发条件见 09 §4.1。仅剩余 ≥ 8 s 时启动：rewrite invoke 总预算 ≤ 3 s（含 Router 内重试 / 降级），补检索整轮共享 ≤ 3 s，至少保留 2 s 收尾；两步也受原 run deadline 约束，不延长 deadline |
| 可选相关性评分 | 默认关闭（03 §1.4.3）。仅剩余 ≥ 6 s 时启动，单次 invoke 预算 ≤ 4 s 且不超过 `剩余 − 第二轮保留额`；失败 / 跳过均记 trace 后照常继续。默认每 run 至多 1 次，`grade.second_round` 开启时至多 2 次 |
| 子流程模型调用上限 | 检索子流程（grade ≤ 2 + rewrite ≤ 1 + synthesize 1）合计 ≤ 4 次；默认配置下 ≤ 3 次 |
| 检索补救次数 | 每 run 初次 + 至多一轮补检索，图片新增信息与查询改写共享名额；至多一次 rewrite invoke。重跑 / 恢复沿用 checkpoint 中已占用名额，禁止重置后重复补救 |
| 前端 | 无事件 15 s 提示「仍在处理」；超过 deadline + 5 s 视为断流，走第 6 节恢复 |

补救步骤开始前及 await 返回后检查剩余时间、取消与当前状态；deadline 已到或 run 已取消时，不发新的请求、不应用晚到改写结果、不继续生成卡片。可选改写失败记录原因并回到原知识降级路径，不单独以 error 终止主流程。补检索完成后 synthesize / guide 同样使用剩余 task 预算；不足时用既有预写计划 / 原文 / 升级降级。正常延迟目标保持不变，启用补救的端到端延迟须单独实测。

`retrieval_control` 按 run_id 隔离，检索轮次与 rewrite 名额先提交 checkpoint，再发起对应外部操作（复用既有 prepare / execute 拆分方式）。恢复发现名额已占用但没有完成结果，按失败 / 不确定降级，不重新发起同一补救；新用户输入的新 run 才重新分配名额。仅在节点局部变量加计数不足以满足恢复后的次数约束。

## 9. Schema 生成与校验

- 事件、动作、快照的 Pydantic 模型位于 `contracts/` 包，`make contracts` 生成 `contracts/events.schema.json`、`actions.schema.json`、`snapshot.schema.json` 与前端 `src/types/*.ts`。
- CI 步骤：重新生成并与提交内容比对，不一致则失败。
- 共享 fixture：`contracts/fixtures/*.json` 包含 A1–A3 与故障场景的完整事件序列；后端流式测试和前端 reducer 测试消费同一批文件。

## L3 增量（2026-09-14，票 51）

沿用 card_id/input_token/target_issue_id/expected_version 校验，新增卡片动作 confirm_context、confirm_proposal、decline_proposal、skip_retake、rate_satisfaction。新增事件 context_card、proposal_card、execution_card、retake_card、rating_card、case_changed，实时流与快照共享载荷。动作与事件的完整字段以 contracts/schema 为准。EmotionLevel 保留 anxious 解析兼容，由 reduce 转换为 dissatisfied。人工审批输入 kind=human_decision 仅供管理端经过案件校验后投递。
