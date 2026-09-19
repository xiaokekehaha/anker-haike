# 任务拆解

- [x] T1 词表：power_bank 加「自身回充慢」族，判别题收录，版本号升级
- [x] T2 计划库：证据锚点 ports#c1/#c2、`pb_737_recharge_slow`、`pb_input_check` 症状码、版本号升级
- [x] T3 故障卡：A1289 与通用卡同步
- [x] T4 synthesize / retrieve：模型可选集合不按码过滤、码内排前；降级排序保持按码过滤（见 addendum 偏差 1）
- [x] T5 decide_next：scope_conflict 提问、outside_confirmed_scope 跳过、按序取第一个动作
- [x] T6 graph：ask_observation 范围分支写 symptom_interview；retrieval_basis 与 reassess 短路；状态字段
- [x] T7 测试：更新既有五处期望；新增 `test_conversation_scope_conflict.py`
- [x] T8 lint、相关测试、addendum
