# 2026-10-09 修复与验证

## 实现

1. 安全否定：`rules/service.py` 允许否定短语中并列出现普通外观异常和安全词，解决“未见明显破损或烧焦”的误报。仍在标点、部件名、转折或未知实义词处停止，不把“未见冒烟，滚刷烧焦”当成无风险。采用有界词法识别，不能宣称覆盖所有自然语言否定。
2. 候选恢复：`sessions/graph.py` 首批合成无可用方案且存在因条数/字符预算被裁掉的证据时，用相同单次预算补评估一次。只读未进入首批的候选，记录 context_recovery，不重查知识库。预算不足时跳过；恢复模型失败时不得把检索排序降级为可执行方案。正常首批命中不增加调用。
3. 前提澄清：`diagnose/synthesize.py` 为 needs_confirmation 增加 clarification_question，校验计划白名单和当前证据引用后保留为澄清候选，与可执行计划分离。回答和已确认观察进入下一次判断；每个连续澄清周期最多问两次，仍无法确认则交人工；已耗尽方案不重新问前提。
4. 人工交接：通用 summarize 复用 CaseService.hand_off，将审核请求和交接摘要原子写入已有案件存储。真实入队后设置 awaiting_human / awaiting_approval，摘要标 requested，才说已提交审核。既不执行服务单，也不宣称真人已接单。服务未配置时保留 prepared，并如实说明只有摘要。
5. 关联状态：`conversation/reply.py` 依据案件真实状态回答交接进度，修复入队后仍说“尚未交接”的矛盾；已入队不再次附加邀请用户转人工的话术。摘要刷新不撤回人工决定或重新入队。

## 验证

新增 `tests/test_diagnosis_recovery.py` 18 项定向回归，首次四类原始缺陷得到 6 failed / 4 passed；修复后通过。补充交接状态查询回归也先观察失败，再修复通过。

最终命令：

```sh
make lint
cd orchestrator
uv run pytest -q tests/test_diagnosis_recovery.py tests/test_rules.py tests/test_retrieval_candidates.py tests/test_retrieve_events.py tests/test_conversation_round5_boundaries.py tests/test_conversation_escalation_summary.py tests/test_conversation_l3.py tests/test_conversation_flow.py tests/test_conversation_pending_flow.py tests/test_conversation_effects.py tests/test_conversation_recovery.py tests/test_conversation_lifecycle.py tests/test_conversation_original_case.py tests/test_conversation_official_tickets.py tests/test_sessions_human.py tests/test_sessions_clarify.py tests/test_conversation_model_clarification.py tests/test_bakeoff.py tests/test_replay.py tests/test_conversation_answers.py tests/test_conversation_history.py
```

结果：210 passed in 13.26s；ruff 无错误；git diff --check 通过。范围包含原有物流、换货、人工审批、排障卡片、会话恢复、摘要、澄清及前轮修复。

这是 FakeChatModel 和假知识库下的代码回归，不是最新容器的真实模型复测。未部署、未重建容器、未提交 Git。保留工作区已有其他改动。
