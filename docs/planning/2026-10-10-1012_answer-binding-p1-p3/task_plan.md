# 任务清单

- [x] P1-1 先承接再撤卡：reduce_turn 撤卡条件、resolve_command 纠正确认条件、PendingAnswer.step_answer、共用载荷校验、提示词
- [x] P1-2 冲突类澄清不问第二次：_diagnose_outcome 过滤上一轮发过的同一 *_mismatch 澄清
- [x] P1 测试：tests/test_answer_binding.py 7 项
- [x] P2 问句先对事实 + P3 条件步骤（方案 A）：app/guide/fact_check.py，一次 guide.step 调用；tests/test_step_fact_check.py 11 项
- [ ] 用户决定：输入预算是否提高（见 progress.md 10:58）
- [ ] ci-local、make up、多轮场景与 63 单复测
