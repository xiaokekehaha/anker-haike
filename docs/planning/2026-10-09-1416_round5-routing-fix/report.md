# Round5 三单修复结果

## 变更

- T7：查件失败纠正绑定整个当前输入的明确物流语句，只移除引用该语句的错误故障事实。混入其他设备或不认识的独立描述时不覆盖整句。提示词明确区分追踪对象与设备对象。
- T56：零/单候选的未知业务对象需要补信息，不能声称存在多个订单，也不复用唯一旧订单。当前故障求助有原话和现象引用时保留排障任务；故障背景本身不产生任务。“只查保修”的明确限制可纠正模型错误优先级，故障事实保留。仅拒绝一台设备排障不删除另一台设备的独立诉求。
- T61：现有 diagnose.synthesize 调用必须输出适用性及逐字覆盖的有效症状。只有 supported 且至少覆盖一条真实症状、引用有效证据的假设进入计划列表。模型有效空结果或全部不适用时不再回填检索候选。入口条件与待检查的原因分开，客户没报错误码不自动拒绝资料。交接保留所有故障事实并标记尚无适用步骤的项目，对用户明确说明未能确认适用官方指导。
- 无工单编号、订单号、固定产品 ID 的生产特判；没有改官方数据、检索阈值、grade 开关、MAX_GUIDES、前端或依赖。

## 验证

1. 15 个相关测试文件合计 **168 passed**，覆盖订单焦点、物流/保修、原官方案例、会话效果、摘要、检索候选、上下文预算、回放及模型评测。最终提示词小幅澄清后相关62项再次通过；最终R5说明补充后摘要/边界相关测试再次通过。`make lint`、`git diff --check` 均通过。
2. 真实模型组件验证 **11/11**：T7/T56各两次；同时查件与设备故障；只查保修；T61拒绝不适用资料；T35保留正常说明；扫地机毛发缠绕、吸奶器弱吸力、摄像头模糊三个正向基准。`model-probe.json` 保存结果。最终 intake 提示词明确区分缺参/歧义后六项再次通过，见 `intake-final.json`。
3. 首轮真实组件验证曾发现“只查保修”反例失败；保留 `model-probe-initial.json`，修正后通过，不覆盖失败证据。

相关文件：test_conversation_round5_boundaries.py、test_business_context.py、test_bakeoff.py、test_replay.py、test_conversation_l3.py、test_conversation_official_tickets.py、test_conversation_answers.py、test_conversation_flow.py、test_conversation_effects.py、test_escalation_summary.py、test_conversation_escalation_summary.py、test_retrieval_candidates.py、test_context_capacity.py、test_context_metrics.py、test_summary_polish.py。

## 证据边界

- 单测全部使用假模型与隔离业务/知识运行时；真实组件探针与单测分开运行。
- 真实模型验证的 T61/T35 复用已保存的候选顺序，取官方全文按当前预算重新打包；它验证理解/方案选择，不是重新检索或部署后的完整会话测评。
- 语义适用性依然需要模型判断；新接口要求其明确判断与覆盖，代码验证输出并保留弃答，而不是保证任意自然语言均不会误判。
- 没有部署/重建容器、提交 Git 或写入业务数据库。当前运行容器仍是修改前代码。T46/T48未纳入本轮实现。
