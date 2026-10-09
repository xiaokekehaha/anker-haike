# 证据

- 页面：localhost:5173/admin/sessions/faeefe0ad4cf497881a5a3610702e9e1。
- 观测台：产品 Omni E28 / T2352，故障码 3212，滚筒拖布卡住。
- 共 2 轮、1 个步骤；第 1 轮用户消息，第 2 轮步骤反馈；当前等待上传凭证。
- 初始工作区已有 Makefile、README、评测报告及其他未跟踪文件变更，本次不触碰。
- 只读 snapshot：仅一张 step_card，plan_id=qa_rv_0147，step_id=s1，feedback=not_solved；当前 stage=context、pending_input.kind=upload_receipt。
- journey：第二轮 understand → apply_action（verify=escalate / R1）→ escalate → service_context → prepare_receipt → await_input，所有节点 status=ok。
- 当前代码支持 steps 型逐步发卡，answer 型整条答案一张卡；decide_next 限制一条指南执行完仍未解决后进入后续服务。
- 待验证假设（顺序）：官方原文只有一个排障动作；解析遗漏原文步骤；推进规则跳过已有步骤。

## 结论

符合现行实现和 2026-10-08 迁移后的推进规则。多步骤能力仍保留，本会话命中的原文只有一个编号步骤，并非前端丢卡或解析遗漏。

1. `data/official/qa.yaml:2971` 的 rv-0147：一个编号步骤，要求取下污水箱、检查并清理滚筒缠绕物，附安装视频；Tips 仅提醒清理地面线缆，没有第二个编号步骤。
2. `app/official/qa_index.py` 将不足两步且无质保结论的指南归为 answer；`app/plans/qa.py` 把该说明生成一张步骤卡，末步 not_solved → EXHAUSTED。
3. `app/diagnose/decision.py:200` 在一份指南耗尽且已有 not_solved 时返回 guide_exhausted，后端实际进入 service_context / prepare_receipt。
4. `docs/planning/2026-10-07-1543_organizer-materials-replan/remaining_work.md:145` 记录：一条官方指南走完仍未解决即进入质保判断，不再连续换相近指南。相关变更见 47902b3、8229981（2026-10-08）。
5. 离线调用实际 QAIndex、计划库、apply_feedback、decide_next：rv-0147 → 1 步 → guide_exhausted；对照 rv-0481 → 5 步 → s2。捕获会话的步骤正文与计划证据正文完全相同。

## 产品建议

- 必要的体验改进：在索要订单前说明“该故障的官方排查已完成，仍未解决，接下来核实保修信息”，让用户知道流程为何切换。
- 可选的交互细化：把原文同一编号内的动作拆为更细的确认步骤，但这属于粒度调整，需要保留原文动作与顺序，不能凭空补出新的排障方法。
- 本轮仅诊断，不修改产品行为或数据，不提交。
