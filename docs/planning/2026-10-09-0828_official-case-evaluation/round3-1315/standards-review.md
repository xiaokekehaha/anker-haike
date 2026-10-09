# Standards

独立审查结果：2 项规范违例、1 项设计启发式问题。8 个被审文件完整读取；审查 diff 与固定快照一致。

1. **新增函数内导入。** `orchestrator/tests/test_eval_tickets.py:19`（另有第 29、31 行）及 `orchestrator/tests/test_conversation_official_tickets.py:488` 违反 `AGENTS.md`“只用顶层导入”。应移到模块顶部。当前 Ruff 配置未启用对应规则；既有内联导入不列入本次发现。
2. **新增明确结构仍以 Any 兜底。** `orchestrator/app/evaluation/live_tickets.py:95` 的 `sop_passed(case: dict[str, Any], …)` 只需要 `sop: str`、可选 `sop_also: list[str]`，不存在难以表达的类型。违反 `AGENTS.md`“后端不用 Any 兜底”。建议定义准确的评测用例类型。
3. **可能的 Feature Envy / Duplicated Code（设计判断）。** `orchestrator/app/sessions/l3.py:635` 的新节点直接遍历案件内部 events 判断是否交接，再执行 transition → record_review_request → _record_handoff；与 await_human 的写入流程重复，但去重规则不同。建议将交接及去重集中到 CaseService，节点负责回复和路由。此项不是硬性规范违例。

Standards 合计：2 项规范违例、1 项启发式问题；规范问题涉及新增导入方式和类型表达，启发式问题涉及交接规则分散。功能与需求差异由 Spec 轴单独报告。
