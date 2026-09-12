# 36: 出口规则 R1 / R1b / R1c / R2 与 A1 完成

**What to build:** CP-verify 判定：executed ≥ 4、skipped ≥ 3、合计 ≥ 6、计划耗尽且无 ≥ 0.3 的下一计划 → escalate；solved → 结束语流式 → done(completed)。至此 A1 排障成功全程可演示。

**Blocked by:** 35（反馈推进、计数器与计划切换）

**Status:** ready-for-agent

- [ ] A1：两步后点「已解决」→ 结束语 → done(completed)，前端回到 idle
- [ ] 连续 4 次「仍有问题」→ R1 升级摘要，摘要含已执行步骤与结果
- [ ] 连续 3 次「无法操作」→ R1b 升级
- [ ] 每次升级判定带规则编号写入结构化日志与 summary.reason

**设计依据：** 09 §3.4；02 §4.1
