# T9 多诉求：先持久化交接，再推进其余任务

对应 Codex 提案 [spec_2026-10-09_t9_request_completion.md](../codex/spec_2026-10-09_t9_request_completion.md) 的最小实现。

## 问题

T9 一句话两个诉求：问 Anker008 主机物流；未发货则先暂停。2026-10-09 11:48 三次复测都只回了一句「已转交同事」，案件仍 open、无交接记录，物流任务永远 pending。用 FakeChatModel 固定意图可以确定性复现，与模型抽样无关。

## 根因

1. `tasks.py` 把 `order_change` 优先级排在物流之前，队首总是 `order_change`。这是设计意图，不改。
2. `service_context` 的 NOT_EXECUTABLE 分支只 `say` 文案后 `finish(state, "commit_issue")`。`finish` 只在 `completed_task_intent` 非空时回到任务队列，而该字段只有 consult / execute / track 会写，主诉求直接进来时为空，于是整轮结束。
3. 即使回到 `advance_tasks`，空的 `completed_task_intent` 被默认成 `report_problem`，`order_change` 仍 active，`next_task` 看到有 active 任务就不选下一个。
4. 「passed your request to a colleague」是硬编码常量，分支里没有调用交接，案件只停在 `order_identified`。
5. `live_tickets.terminal_of` 只要回复含该短语就判 `order_change_human`，且 T9 接受集合是 `{logistics_presale, order_change_human}` 二选一，所以丢物流和丢暂停都算通过。

## 改动

- `app/sessions/l3.py`：新增 `hand_off_request`，先 `transition(awaiting_approval)` + `record_review_request` + `record_handoff`（摘要带客户原话），再输出文案；案件已在队列且诉求相同时跳过写入。`service_context` 与 `propose` 的 NOT_EXECUTABLE 分支都走它。新增 `waiting_human`：把对应任务记 `waiting_human` 并路由到 `advance_tasks`，`await_human` 同样使用。`advance_tasks` 读 `task_outcome` 决定任务终态。
- `app/conversation/tasks.py`：`next_task` 增加 `outcome` 参数（done / waiting_human）；`enqueue` 把 `waiting_human` 任务视为已存在，重复诉求不再入队。
- `app/sessions/graph.py`：`SessionState` 加 `task_outcome`；`await_human` 可达 `advance_tasks`。
- `app/evaluation/live_tickets.py`：`terminal_of` 改为 `terminals_of` 返回多终点；`order_change_human` 只在案件 `awaiting_approval` + `review_requested` 为不可执行诉求 + 有交接摘要时成立；新增 `sop_passed`，`sop` 与 `sop_also` 每项都必须到达；`run_case` 读案件详情接口取证据。
- `data/eval/tickets/cases.yaml`：T9 加 `sop_also: [order_change_human]`，并在注释里登记该终点。

未做（可选复杂度）：三次案件写入收敛为一次事务、稳定请求编号的幂等重放。当前内存与 Postgres 存储的 `transition` / `record_*` 各自原子且按内容去重，决赛前不需要。

## 验证

- 新增回归：`tests/test_conversation_official_tickets.py`（T9 两种意图顺序、重复诉求不重复入队、单独暂缓诉求干净结束）、`tests/test_l3_experience.py`（队列 waiting_human 语义）、`tests/test_eval_tickets.py`（话术不是转人工证据，T9 两终点缺一不可）。
- 相关测试文件全部通过，`make lint` 零告警，确定性 63 单评测仍 passed / 35 deterministic。
- 2026-10-09 13:15 `make up` 重建（镜像内 l3.py / tasks.py / live_tickets.py 哈希与工作区一致）后，真实模型按原输入重跑 T9 三次，会话 13:15:09 / 13:15:14 / 13:15:18，报告 `reports/eval/20261009T0515{09,14,18}Z_live_tickets.*`。三次一致：
  - 回复先说明不能改单已转交，再「Next up: delivery status」，列出主机预售 2026-10-20 发货、滤网 2026-09-12 已送达；
  - 案件接口 `awaiting_approval`，事件 order_identified → status_changed → review_requested → handoff_summary，交接摘要原因为「暂缓发货 / 取消 / 改购需人工办理」加客户原话；
  - 任务队列 order_change=waiting_human、logistics_query=done，无待办卡片；
  - 评测终点 `order_change_human + logistics_presale`，意图 / SOP 100%，幻觉 0，单次 4.0–4.7 秒。
  三次同样输入只说明样本稳定，确定性回归仍以上述单测为准。

## 2026-10-09 13:15 复核（round3）后的补修

复核报告 [round3-1315/report.md](../planning/2026-10-09-0828_official-case-evaluation/round3-1315/report.md) 四项 Spec 缺陷中三项与现场多轮操作相关，本轮修复；存储半途失败一项需要数据库在两次写入之间中断，比赛碰不到，不做。

根因是粒度错配：诉求的身份是「类型 + 原话」，上一轮按类型去重；任务能否推进取决于等待原因，上一轮按优先级推进；人工结论回来时没有更新关联任务。

改动
- `app/cases/service.py`：新增 `CaseService.hand_off`，一次 `mutate` 完成进队列、记诉求、写摘要。同一诉求重试不重复写；同类型原话变了记 `request_changed` 并重写摘要；案件已 `rejected` 时先回 `proposing` 再入队，避免非法迁移。
- `app/conversation/tasks.py`：`next_task` 加 `only` 参数限定可推进的意图；新增 `settle` 按人工结论收尾等人工的任务；`enqueue` 对等人工任务的改口只更新原话，不另起任务。
- `app/sessions/l3.py`：`hand_off_request` 改调 `CaseService.hand_off`；`advance_tasks` 在有任务等人工时只推进查询类任务，排障与办理保持 pending、阶段保持 awaiting_human；`apply_human_decision` 用 `settle` 更新关联任务（批准 / 驳回记 done，要求补充回 pending）。
- `app/evaluation/live_tickets.py`：评测用例终点标注改为 `SopExpectation` TypedDict，去掉 `dict[str, Any]`。
- 测试文件函数内导入移到顶层。

回归
- `tests/test_conversation_official_tickets.py`：改口后人工看到最新原话且只有一份等人工任务；驳回后任务收尾、再提诉求重新入队且迁移链为 awaiting_approval → rejected → proposing → awaiting_approval；换货卡上请人工后不推进排障、阶段保持 awaiting_human。
- `tests/test_l3_experience.py`：`hand_off` 去重 / 改口 / 驳回后再入队；等人工时只推进查询类任务、`settle` 与改口更新。
- 相关 7 个测试文件 124 条通过，ruff 零告警。

### 2026-10-09 13:42 重建后真实模型复测

`make up` 后镜像内 l3.py / service.py / tasks.py 哈希与工作区一致。T9 首封三次（13:42:25 / 13:42:30 / 13:42:36，报告 `reports/eval/20261009T0542{25,30,36}Z_live_tickets.*`）与 13:15 一致：回复先转交再答物流，案件 awaiting_approval 且事件链完整，队列 order_change=waiting_human、logistics_query=done，终点 order_change_human + logistics_presale，幻觉 0。

另在第一个会话上走多轮：后台驳回 → 客户说「Then please cancel the whole Anker008 order instead.」。驳回后任务收尾为 done、阶段 done；第三轮无运行错误（修复前此处报非法迁移）。但模型把这句判成 order_query，确定性守卫 ORDER_CHANGE_WORDS 只匹配 `cancel (the|my|this) order`，「cancel the whole … order」不命中，于是没有补成 order_change，系统答了订单信息与物流而不是再次转人工。这是意图识别词表覆盖问题，不属本轮交接修复；是否放宽词表另行决定。
