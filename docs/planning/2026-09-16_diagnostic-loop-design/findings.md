# 已核实事实

- f30 会话只有 rv_power_supply 一个候选，执行两步后 next_on=EXHAUSTED；verify 返回 R2，next_confidence=null。
- apply_feedback 记录 feedback/note/title/source 并推进计数和游标；反馈契约以 solved/not_solved/cannot_do 为中心。
- verify 同时包含 executed>=4、skipped>=3、executed+skipped>=6 的提前结束条件；单改 R2 仍有其他独立出口。
- graph 的 guide 另有情绪动作 prefer_proposal_over_more_steps 且 executed>=2 的 R2 出口。此次并非该出口触发。
- symptom_taxonomy 已有“放回基站后，设备有正常的充电指示或充电语音吗？”。这说明部分判别知识已存在，但当前计划反馈没有将具体观察接回问诊。
- config/plans.yaml 中两步 instruction 分别要求确认电源灯/触点、观察五分钟是否开始充电，但 expected_result 都强调恢复使用；因此反馈无法区别检查结果正常但故障仍在、异常或尚未完成观察。
- 计划声明 source 为 kb_manual 并不自动证明新扩展内容适用于全部型号；新增设备操作与技术判断仍需核对来源和适用范围。
- 本轮仅设计；部署核查细节见 docs/codex/spec_2026-09-16_f30_r2_diagnosis.md。
