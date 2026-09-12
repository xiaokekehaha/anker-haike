# 16: 升级摘要 escalation_summary 与 SummaryCard

**What to build:** escalate 的 summarize 节点不依赖模型即可生成结构化摘要（产品、问题、观察、假设、步骤、原因、情绪、凭证状态 not_collected、model_trace），发 escalation_summary 事件；前端 SummaryCard 渲染并一键复制。先以 R4 安全升级路径打通。

**Blocked by:** 06（前端 reducer、SSE 解析与 ProgressBar）、15（规则服务骨架与 CP-in 安全升级）

**Status:** done（2026-09-12；SummaryCard 随前端集成完成，见票 06）

**Owner:** 后端 Claude Code B（`orchestrator/app/escalation/`、graph.py escalate 节点）；前端 SummaryCard 建议 Codex 认领（`frontend/src/components/SummaryCard.tsx`）

- [x] 用户首句触发安全词 → 安抚 → escalation_summary → done(completed) 全链路可演示（后端事件序列 run_started → progress(intake) → progress(escalate) → message_start / message / message_end（固定安抚文案，不调模型）→ escalation_summary → done(completed)；快照 timeline 折叠出 assistant_message + escalation_summary。前端渲染待 SummaryCard）
- [x] summary 对象层级与契约一致，receipt.status=not_collected（用 contracts 的 EscalationSummary 构造并 model_dump，事件过 parse_event 校验）
- [x] SummaryCard 复制内容为可读文本，含全部五要素（`summaryToText` 与后端同款八行；Cards.test 断言 clipboard 文本含产品 / 问题 / 观察 / 假设 / 已执行步骤 / 升级原因 / 凭证）
- [x] 模型不可用时摘要仍能生成，model_trace 标 summary_polish=skipped（`build_summary()` 纯规则渲染；model_trace 追加 `{task: escalate.summary_polish, model_used: skipped, attempts: 1}`，契约 attempts ≥ 1 故用 1 表示「未发起」）

**设计依据：** 08 §5；09 §4、§5.1

**实现记录（2026-09-12，Claude Code B）：** `app/escalation/summary.py`（`build_summary(state, reason, lane)`、`summary_card_id = uuid5(session, reason)` 稳定、`reassurance_text(reason)` R4 / R3 固定文案、`summary_to_text`）；graph.py `escalate` 节点发安抚消息与摘要卡并把 `escalation_summary` 写入状态。tests/test_escalation_summary.py 3 项。

**给前端（Codex）的接口说明：** 事件 `escalation_summary{card_id, summary}`，summary 形状见 contracts/schema/events.schema.json 的 EscalationSummary；快照 timeline 项 `kind=escalation_summary`。SummaryCard 复制文本建议与 `summary_to_text` 一致：【产品】【问题】【观察】【假设】【已执行步骤】【升级原因】【情绪】【凭证】各一行。
