# Claude 修复复核

基线：HEAD a1a8798，待审为工作区未提交修改，使用 git diff a1a8798 -- <scope>。不是已提交的分支改动，因此不使用三点 diff 遗漏工作区。

需求来源：docs/codex/spec_2026-10-09_t9_request_completion.md；实现说明：docs/claude/spec_2026-10-09-1239_t9-handoff-then-advance.md。

范围：app/conversation/tasks.py、app/sessions/l3.py、app/sessions/graph.py、app/evaluation/live_tickets.py、data/eval/tickets/cases.yaml，及三份相关修改测试。operation_conditions 与其他测试存在并行修改，真实链路结果将包含当前完整运行版本，需记录哈希。

1. 规范与需求两个独立审查；完整阅读被审文件，确认实际问题而非仅列设计偏好。
2. 跑相关文件级回归；补充隔离验证共享人工交接入口、半途失败、重复请求等风险。临时脚本保存后执行并清理，不改应用实现。
3. 核对容器与工作区代码一致；按 round2 原文、原附件、停止条件重跑 8 个案例，T9 加两次重复，T1 加两次重复。
4. 客户文本、SSE、快照、观测、案件详情保存并逐项核对官方事实；未验证范围不能声称无影响。

不提交代码，不执行真实退款/换货，不补造故障照片或 SN，不更改他人文件。
