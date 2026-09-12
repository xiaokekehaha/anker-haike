# 37: rediagnose 中途补充与纠正

**What to build:** guide / verify 阶段用户在 Composer 发送自由文本或图片，前端提示「补充信息将重新判断故障」，提交为 rediagnose 动作；后端新输入过 CP-in，回到 diagnose 重新汇总，保留 steps_executed 与 counters。

**Blocked by:** 36（出口规则 R1 / R1b / R1c / R2 与 A1 完成）

**Status:** ready-for-agent

- [ ] 排障中补充「其实还有异响」→ plans_ranked 变化 → 新步骤卡
- [ ] 补充文本含安全词 → R4 升级
- [ ] steps_executed 在 rediagnose 后保留并出现在最终摘要
- [ ] 有 active run 时 rediagnose 被 409 not_allowed_now

**设计依据：** 09 §1；08 §4；05 §2
