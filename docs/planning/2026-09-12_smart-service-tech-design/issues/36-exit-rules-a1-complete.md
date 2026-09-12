# 36: 出口规则 R1 / R1b / R1c / R2 与 A1 完成

**What to build:** CP-verify 判定：executed ≥ 4、skipped ≥ 3、合计 ≥ 6、计划耗尽且无 ≥ 0.3 的下一计划 → escalate；solved → 结束语流式 → done(completed)。至此 A1 排障成功全程可演示。

**Blocked by:** 35（反馈推进、计数器与计划切换）

**Status:** done（2026-09-13；CP-verify R1/R1b/R1c/R2 随票 35 落地于 app/guide/verify.py，本票补 close 节点：solved / next_on=DONE → 结束语流式 → progress(done) → done(completed)）

**Owner:** Claude Code A（2026-09-12 认领；`app/guide/`（CP-verify R1/R1b/R1c/R2））；接手会话 2026-09-13 完成 close 节点与收尾

- [x] A1：两步后点「已解决」→ 结束语 → done(completed)，前端回到 idle（graph.py `close` 节点：固定模板结束语（带起效步骤标题与产品名）以 message_start / message / message_end 下发，不调模型，回放包零 miss；stage=done，visible_messages 记 kind=closing；前端 reducer 对 done(completed) 已回 idle，ProgressBar 把 done 映射到「处理结果」）
- [x] 连续 4 次「仍有问题」→ R1 升级摘要，摘要含已执行步骤与结果（verify.py LIMITS R1=4；build_summary.steps 来自 steps_executed，summary_to_text 输出【已执行步骤】title（feedback）；test_cp_verify_limits_r1_r1b_r1c）
- [x] 连续 3 次「无法操作」→ R1b 升级（skipped ≥ 3；R1c executed+skipped ≥ 6；R2 计划耗尽且下一计划 < 0.3，test_exhausted_with_low_confidence_next_plan_escalates_r2）
- [x] 每次升级判定带规则编号写入结构化日志与 summary.reason（_apply_step_feedback 记 cp_verify 日志 extra.rule_id / counters；close 记 a1_complete；EscalationSummary.reason.rule_id 取 escalate_reason，REASON_TEXT 覆盖 R1/R1b/R1c/R2）

**设计依据：** 09 §3.4；02 §4.1

**验收（2026-09-13）：** 后端 392 项、前端 123 项、ruff 通过；`haike-replay verify a1_hair_wrap` 零 miss（新增结束语不调模型，录制包无需重录）。
