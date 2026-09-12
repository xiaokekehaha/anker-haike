# 35: 反馈推进、计数器与计划切换

**What to build:** step_feedback 三态经 apply_action 写入 steps_executed，更新 counters（not_solved → executed+1、cannot_do → skipped+1），按 next_on 推进 plan_cursor；EXHAUSTED 时若下一计划 confidence ≥ 0.3 则切换并跨计划去重相同 instruction_src。verify 无 LLM 参与。

**Blocked by:** 34（步骤卡下发 guide.step 与 CP-pre-step）

**Status:** ready-for-agent

- [ ] 「仍有问题」→ 下一步卡；「无法操作」→ 按 next_on.cannot_do 推进
- [ ] 首计划耗尽后自动切到第二计划首步，plans_exhausted+1
- [ ] 相同 instruction_src 的步骤被跳过
- [ ] verify 节点耗时 < 100 ms 且无模型调用

**设计依据：** 03 §1.6；09 §3.3、§3.4
