# 数据与统一协议契约

所有字段/表/接口变更是设计提案，尚未迁移或生成代码。命名以本文为 V2 设计基线，执行规则见 [developer-handoff.md](developer-handoff.md)；历史会话可清理，运行时只保留一套最新契约。

## 1. 权威数据与派生数据

| 数据 | 权威来源 | 派生与恢复 |
| --- | --- | --- |
| 用户原始输入/动作、助手实际输出、工具结果 | session_events 的不可变事件 | ConversationHistory 按 seq 折叠；不从摘要恢复原话。 |
| 当前 issue/facts/risks/pending/steps | LangGraph V2 checkpoint | 通过已校验 state_committed 增量和 checkpoint 检查恢复；禁止靠重调 LLM 重算已提交变更。 |
| 请求幂等 | session_inputs 接收账本 | 指向 input_received 事件、run 与提交状态；不另存一份可编辑原文。 |
| 早期问答摘要 | conversation_summaries 派生缓存 | 可丢弃重建，不改变业务事实。 |
| 最新摘要卡、聊天界面、analytics | 事件 + checkpoint 投影 | 最新摘要与历史 revision 各自可查。 |

新增物理表限上述 session_inputs/conversation_summaries；Issue/Facts/Risks 首期存在 checkpoint 的类型化结构，不先建第二套可写业务主库。

session_inputs 统一承接消息和动作幂等，V2 移除 session_actions 的读写与表定义；先按 cutover.md 清理旧行再迁移删除旧表，不同时维护两份动作账本。sessions 增加 published_checkpoint_id 和 last_state_commit_seq，version 改为显式已发布业务版本。session_events 增加 event_id/visibility，保留原复合主键，并增加 UNIQUE(session_id,event_id)；内部与公开事件共用序号、分别校验 schema。

## 2. 统一问答记录

`ConversationEntry` 是完整条目，不是一段流式 delta。字段：

| 字段 | 定义 |
| --- | --- |
| entry_id | 稳定 ID。用户条目由 input_id，助手条目由 message_id，动作由 action_id 派生。 |
| session_id / run_id | 会话与执行 ID；run_id 不是长期用户 ID。 |
| issue_id / device_ref_id | 归属。输入时不确定可空，另有带来源的归属变更；不能篡改原始输入。 |
| kind / role | message/action/tool/card；user/assistant/tool。按钮动作不可假装成用户原话。 |
| first_seq / last_seq | 所覆盖事件的序号范围；排序以 first_seq 为主，seq 不要求连续。 |
| received_at | 用户/动作请求到达服务器时间。助手条目可空。 |
| started_at / completed_at | 助手/工具开始和完成时间。未完成时 completed_at=null。 |
| recorded_at | 事件实际写入时间；同秒不同事件仍按 seq 排序。 |
| time_source | server/unknown；未知时间保留 null，不造毫秒。 |
| text / payload / attachments | 文字、受控动作内容、图片引用及分析状态；原图不进入文字记忆。 |
| reply_to_input_id / references | 回答关联及其明确引用消息；一轮可以有多段回答。 |
| status | completed/aborted/streaming/failed/replaced；取消片段不算已完成指令。 |
| source_event_ids | 原始来源，可回查。 |

事件标识 V2 采用 `event_id`，同时保留既有 `(session_id, seq)` 主键。记录 UTC ISO 8601 带偏移，UI 按会话 timezone 展示。用户设备时钟提供的 client_sent_at 仅作辅助，不作为权威顺序。

用户描述的“昨天就坏了”存入事实的 occurred_at/time_expression/precision，不能放到该条消息的 received_at。相对时间以该输入的 received_at 为基准，重试/回放不取新时钟。V2 新增 conversation_timezone 配置（默认 Asia/Shanghai），创建会话时冻结到 sessions.timezone，并在快照返回；当前 Settings 尚无此字段，本期不新增客户端时区修改接口。

### 折叠规则

- 按 message_id 合并 start/delta/end，replaces 保留引用，被替换文本不作为当前有效回答。
- 原始角色保留；展示过但中断的片段只作为带状态的历史数据。用户引用它时可解释其未完成状态。
- 同一 input_id/action_id 重放只有一个条目；相同文字但不同 input_id 是两次真实发言，不按文字去重。
- action 显示“请求人工/选择型号/反馈无效”等受控标签并有时间，原始 action_id 留在技术追踪。
- 工具结果关联 tool_id、输入、issue、开始/完成时间；失败和图片过期不伪装成功观察。
- as-of 视图严格读取 `seq <= through_seq`；后续摘要和归属变更不能提前出现在历史状态。

## 3. 问题与事实状态

建议 V2 checkpoint 顶层：

```text
state_schema_version = 2
active_issue_id
issues: {issue_id: IssueState}
device_refs: {device_ref_id: DeviceRef}
risk_cases: {risk_id: RiskCase}
unassigned_risk_ids: [risk_id]
conversation_preferences
context_revision
last_applied_input_id
pending_effects
committed_version
turn_work
```

`IssueState` 包含：issue_id、status、opened_by_input_id、opened_at、device_ref_id、product_selection、facts、risk_case_ids、steps_executed、counters、current_evidence_ids、plan_cursor、pending、handoff、issue_revision。每个问题独立增量更新。

- `facts` 中每条 Fact：fact_id/kind/value/source_kind/source_entry_ids/issue_id/device_ref_id/status/revision/recorded_at/occurred_at/time_expression/precision/supersedes。
- source_kind=user_report/user_confirmed/tool_verified/model_hypothesis。用户说“清过滤网”不意味着效果好；助手建议“清理滤网”不意味着用户执行过。
- status=active/retracted/superseded/disputed。原始记录不删除；当前上下文只用有效或明确标识为冲突的事实。
- `FactPatch`：add[]、retract[{fact_id, reason, source_input_id}]、replace[{fact_id,new_value,source_input_id}]、clarify[]。每个目标必须来自本会话可见事实，禁止模型随意构造 ID。
- replacement 首先验证来源与主体，旧事实 superseded、新事实 active；没有目标的“刚说错了”只生成 clarify，不撤回任意最近事实。
- patch_id 由 input_id + operation_index 稳定派生；重试不得二次改变步数或 fact revision。

`DeviceRef` 是本会话内实体：device_ref_id、category、model_candidate/confirmed_sku、identity_status(provisional/confirmed_by_user)、source_ids。两台同型号设备必须有不同引用；品类相同也不能自动合并。

RiskCase 的实体定义统一存顶层 risk_cases 字典；IssueState.risk_case_ids 与 unassigned_risk_ids 只引用 ID，避免跨 issue 复制同设备风险。

`Pending`：pending_id、kind、issue_id、card_id、input_token、created_at、created_seq、payload、status、superseded_by、basis_refs。status=pending/suspended/consumed/invalidated；kind 沿用 select_product/step_feedback/upload_receipt/confirm_receipt。basis_refs 包含产品确认版本、计划/步骤版本、必要事实 ID；不以任何 issue_revision 变化都作废卡片。input_token 是业务待办凭据；请求、事件、快照统一使用 input_token，删除 interrupt_id 兼容别名。

公开 version/expected_version 使用 sessions.version：首次为 0，每个 run 首次发布 commit_turn 时 +1；重放、事件交付、摘要缓存完成不增加。checkpoint 内 committed_version 是该值的权威恢复来源，published_checkpoint_id 定位该业务状态。checkpoint step 不再用于公开版本。context_revision 在有效事实、风险、偏好、active issue/pending 等理解依据变化时 +1，issue_revision 仅在该 issue 业务变化时 +1；解释性回答仅增加公开 version。后台摘要新消息水位与业务修订分别检查，不能混用。

## 4. 风险、人工与单轮决策

`RiskCase`：risk_id、rule_id、source_input_ids、reported_at、issue_id?、device_ref_id?、status、restriction、policy_version、last_evidence_seq、dispute_refs。未知主体的 ID 放 unassigned_risk_ids，不能自动绑定旧设备。操作许可需检查当前设备关联及尚未澄清的潜在同设备风险。

`Handoff`：handoff_id、issue_id、status、reason_refs、prepared_at、requested_at、accepted_at、external_request_id?、last_error?。当前无外部适配时只允许 prepared；后续真实接口使用稳定 idempotency_key=handoff_id。重复按钮换 action_id 也应识别同一尚有效的 handoff，不能重复建外部请求。

`TurnDecision`（本轮瞬态）：input_id、primary_intent、target_issue_id、reply_mode、allowed_operations、pending_effect、escalation_trigger?、reason_codes、source_refs。本轮结束即不再作为下一轮默认路由依据；旧原因仍保留在 RiskCase/Handoff 历史。

移除会话级 escalate_reason 路由字段；本轮原因取 TurnDecision.escalation_trigger，analytics 最终结果从 issue/handoff 历史派生。

## 5. 请求幂等、串行与崩溃恢复

### session_inputs 接收账本（逻辑列）

session_id、input_id、kind(message/action)、payload_digest、run_id、input_event_seq、received_at、deadline_at、base_version、base_checkpoint_id、status(accepted/running/completed/failed/cancelled)、state_commit_version、last_output_seq。

actions 在入口规范化 input_id=action_id；两者共用会话内 ID 命名空间，kind 纳入 digest。收到已有 ID 时先比 digest，再看状态：running 订阅原 run，终态重放原结果；failed/cancelled 不因重发同 ID 新开 run。相同 ID 在版本变化后仍重放，重复动作换 ID 则由 pending/handoff 业务约束去重。

唯一键 `(session_id,input_id)`；payload_digest 包含规范化正文、purpose、按顺序排列的图片内容摘要或已验证引用、目标 issue/card 和动作业务参数；不包含 expected_version、客户端发送时间或本次网络重试元数据。重复 ID 但不同业务载荷返回 409 input_id_conflict。相同 ID 正文相同的重试忽略旧 expected_version，恢复/重放原 run；改变正文需新 ID。

正文规范化仅统一换行符，不压缩内部空白、不删否定和标点；JSON 键稳定排序。digest 使用请求显式传入的 target_issue_id/card/token（缺省记 null），解析出的实际 issue 另存输入关联事件；重试不能用新 active issue 重算旧输入摘要。附件以最终传输字节的 SHA-256 和顺序为准，不包含文件名、随机图片 ID 或上传时间。服务端事件幂等比较同样排除首次落库才生成的 seq/recorded_at，重放保留第一次的元数据。

### 接收事务

1. 会话锁下查 input_id：已有则校验摘要并返回原 run；没有再检查 version/issue/card。
2. 普通新输入遇 active run 返回 409 run_active；不得写半条输入。
3. 新 request_human 可请求取消 active run；先做去重，再发取消信号，不能持有运行完成必须获取的锁去等待。取消结束后重新加锁并复查 input_id/active run，进入同一接收事务。
4. 在同一 PostgreSQL 事务完成 try_start_run、session_inputs 占位、run_started 和 input_received 事件。现有独立方法需要合并为 Store 的 `reserve_input()`，不能只在 router 拼几次非原子调用。
5. 图片先在事务外校验、计算传输字节 SHA-256；新输入的图片正式行与接收账本在同一事务写入。ImageStore 提供接收 conn 的写入接口，现有 put() 不能先独立提交。重复 ID 不新增图片行；图片 ID 从 input_id + 附件序号派生，相同图片不同输入仍有各自归属。数据库失败清理请求临时资源；图片独立过期后，已接收输入仍按账本 digest 重放。

### 状态与输出的协调

checkpoint 与事件虽然使用同一 PostgreSQL，但当前 Saver/Store 各自提交，不能当成同一原子事务。V2 先提交 commit_turn checkpoint（last_applied_input_id、patch_ids、committed_version、pending_effects），runner 再用短事务发布 checkpoint 指针、version 和 state_committed。中间 turn_work 对外不可见。effect 是否已交付以事件唯一键为准，不为每条 delivered 再写 checkpoint；恢复重发已持久化输出，不重新解释或重复应用业务 patch。分阶段故障处理见 developer-handoff.md §2。

新增 state_committed 内部审计事件关联输入、checkpoint/version、经过校验的变更与 effect_ids。它不是一份可独立编辑业务状态；若落日志失败，从 checkpoint 补写。session_inputs 状态是投影，可从 checkpoint/effect 结果对账。

文字流每段先持久化后发送；commit_turn 保存 AnswerSpec 和稳定 message_id，不要求预先生成所有 delta。活跃 run 内模型失败可用新 message_id + replaces 替换；进程重启则将未结束消息标 aborted，以确定性提示收尾，不自动再次调用模型续写。已完整持久化的 message_end(completed) 保留完成状态。取消/崩溃不回滚已发布事实和反馈，前端从快照说明本轮状态已记录但回复未完成。

外部副作用（未来转人工）使用 outbox/effect 与外部幂等键；普通模型回复不产生“真实转接成功”的效果。没有供应商幂等/回执时不得假定 exactly-once。

## 6. HTTP / SSE / Snapshot 统一新契约

前后端同版发布、清理历史后统一使用新契约；不增加协议协商 Header、双解码器或按会话记录的 engine_version。V2 只是本设计版本名称。

- `POST /sessions` 保持无 body 创建，响应为 session_id/version；创建的均为新图状态。
- `/messages` multipart 增加必填 input_id、expected_version，可选 target_issue_id；text/images/purpose 保留。初次发送生成 ID，网络重试复用。服务端支持空 text + 非空 images；纯文字的 purpose 固定 fault，只有实际凭证附件才用 receipt，不能因正在等待凭证就把普通追问变成凭证提交。
- `/actions` 保留 action_id/card_id/expected_version/动作业务字段，interrupt_id 改为 input_token；增加 target_issue_id，新增 new_issue/resume_issue 动作供 UI 使用；删除旧 rediagnose 外部动作，补充/纠正统一走 /messages。显式命令与内部语义命令复用同一验证器。
- `/sessions/{id}` 增加 active_issue_id、issues 简表、last_event_seq、latest_summaries、timezone；pending_input 只从 active issue 的 pending 状态派生。版本和业务字段取 published_checkpoint_id；last_event_seq 是这份快照实际折叠到的水位，不能先读历史再另查 MAX(seq)。一致性与续接算法见 developer-handoff.md §3。
- timeline 所有问答/动作带 issue_id、first_seq/last_seq 和时间；summary 带 summary_id/revision/updated_at/source_through_seq/previous_card_id。
- SSE 基础事件保留 seq/run_id，增加 event_id/recorded_at；message_start 带 reply_to_input_id/issue_id。新增 input_received、issue_changed、pending_changed、summary_updated 等公开类型，内部 state_committed 不向聊天流暴露原始详情；最小事件字段见 developer-handoff.md §3。
- 内部事件被过滤时公开 seq 可有间隔；客户端使用最大已收到 seq 续接，不把间隔当成丢包无限重连。
- 已被清理的 session_id 返回 not_found；前端清除本地旧 session 引用，展示“历史会话已清理，请开始新会话”，不尝试解析旧快照。

同步修改 Python 契约、JSON Schema、生成 TS/Zod、fixtures、所有事件 switch 和请求调用方。用新规范重建 fixtures，保留业务行为回归，不要求旧 JSON 继续通过。静态前端与后端打包一起发布，旧打开页面需刷新后再使用。

## 7. 摘要与界面时序

摘要实体 summary_id 绑定 issue_id/handoff_id；每次有效事实或人工状态变更生成 revision。card_id 由 session + summary_id + revision 稳定生成：同一 revision 重放幂等，后续 revision 不覆盖旧历史卡。

“新问题”“刚说错了”若未形成事实变化，不生成新故障摘要；原问答正常留在历史。最新摘要投影指向最大有效 revision，历史卡显示“此为当时记录，已有更新”及链接，不将未来事实写回旧位置。

聊天中用户/助手均可显示 HH:MM，跨日期显示日期；回顾回答按语义需要引用时间，避免每句带冗长时间前缀。按钮操作形成简短记录，摘要展示更新时间、问题归属和真实人工状态。

## 8. 历史压缩与时间回查

`conversation_summaries`：session_id、summary_id、issue_ids、through_seq、source_context_revision、source_entry_ids、text、generated_at、prompt_version、status(active/stale)、expires_at。

加载历史先选通过版本校验的摘要，再接未覆盖的完整问答；纠正目标若在摘要内，从 source IDs 回查原文并使旧摘要 stale。对“当时说的是什么”执行 as-of 读取，而非取最新事实冒充过去内容。

异步任务只提交派生缓存，CAS 验证来源范围/context_revision/会话未删除；失败直接丢弃，不修改 checkpoint。事件已到期时返回历史不可用，不能用压缩摘要延长原会话寿命。

## 9. 历史清理与统一切换

用户已明确允许清理历史且无需兼容。本次采用停入口、结束运行、清理会话、更新结构、同版发布、冒烟验证后恢复入口的单次切换。

具体范围见 [cutover.md](cutover.md)。不构建旧格式 reader、会话引擎分配表、双图或灰度分流；不迁移挂起 checkpoint。新版本内部的断流、幂等、取消、故障恢复仍须完整实现。

结构迁移仍由 Alembic 管理；不重建产品库、知识库或全数据库。切换失败保持入口关闭并修复，再跑冒烟；不设计带旧会话状态的跨版本恢复。现有会话 TTL 配置保持不变。
