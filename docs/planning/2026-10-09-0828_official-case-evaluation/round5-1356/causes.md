# Round5 问题原因与方案复核

2026-10-09，基于首测、followups、当前代码与离线机制验证。应用未修改，未重新调用真实模型或写入业务数据库。评审时 HEAD 为 38a29b5，orchestrator/config 无未提交差异。

## 五个问题分别如何产生

### T7：把追踪号故障当成设备故障

首测产生 report_problem + logistics_query，复测只产生 logistics_query。系统表现为把 tracking number 后的 “it is not working” 当成设备故障；模型内部为何选择这一路不能仅凭输出证明。

`conversation/interpret.py:169` 的 logistics_correction 能把 order_query 改为物流，也能纠正明确“从未收到”时的排障，但本句未满足这两条纠正规则。`conversation/tasks.py:45` 把排障排在物流之前，于是先追问型号。离线将观察到的意图组合传入同一纠正函数，确认错误分支保留；把唯一变量改为 order_query，则纠正为物流。

应判断“不能用”的对象及对应原文，只修正被误归为设备故障的追踪诉求。不能用“未命中设备关键词”证明没有设备故障，也不能整批清除症状事实。

### T56：故障描述被保留，处理任务却只剩保修查询；未知对象又被说成多订单

保存的 issue 标题是 offline，但 task_queue 只有 warranty_query，没有 report_problem；因此不是故障文字完全没读到，而是没有安排处理它的任务。队列的 business_reference 明确为 ambiguous，subject_id=null，candidate_ids=[]。

`conversation/business.py:115` 接受 ambiguous 时允许零个候选；bind 直接传播此状态。`sessions/l3.py:720` 和 `conversation/answers.py:97` 都将 ambiguous 渲染为 “more than one order”，没有核实候选数。离线用零订单对象复现同一答复。直接缺参应请求订单信息，不能断言多个订单；但只改文案仍不能解决离线故障未处理的问题。

应分开判断当前故障求助与保修反问，避免保修意图覆盖故障诉求。不能把任意 symptom 事实直接当作“用户要求现在排障”：例如“摄像头离线，但先别排障，只查保修”，或历史故障作为退款背景，都不应被强行带回排障。

### T61：资料的故障现象不适用，却通过了方案选择

真实 query 同时保留 “goes off 2 hours early” 与 “cleans not recorded by app”，intake 和 diagnose.synthesize 均成功，未截断上下文。因此两条症状不是在入口丢失。随后发布的 qa_rv_0522 讲的是“7051，已有任务导致定时清扫无法启动”，不解释提前启动，也不解释记录缺失。

`plans/library.py:97` 主要限制产品适用范围；`diagnose/synthesize.py:73` 检查计划 ID、证据 ID 并排序，不独立验证现象是否一致。有效来源不等于对当前问题适用。确定性探针确认同型号、有效证据引用可以通过此过滤，即使现象不对应。保存的摘要未提供原始 hypotheses，因此不能武断断言真实运行到底是模型选错还是空结果被兜底覆盖；可以确定整个选择链未挡住不适用资料。

额外确认：`diagnose/synthesize.py:232` 将模型空列表也归入 all_dropped，随后恢复候选并统一 confidence=0.3，达到 `diagnose/decision.py:114` 的出卡门槛。FakeChatModel 返回空 hypotheses 的离线探针复现了这个行为。这是方案必须覆盖的通用缺口，不等于已证明 T61 真实运行经过了该分支。

应按现象与必要条件判断适用性，保留“无适用方案”的有效结果；无法覆盖的症状进入交接。不能仅因客户没报错误码就禁止使用带码说明，也不能按原始排名分数判断答案可信度。

### T46：把文档排版当成交互类型

官方 bp-0123 同时包含标题、诊断提问、材料请求和实际操作。`official/qa_index.py:129` 按编号拆段，`plans/qa.py:52` 把每段统一生成 solved/not_solved/cannot_do 步骤卡。离线生成的第一步是 Identify the Problem，第二步是 Is the noise continuous or intermittent?，两步却都要求检查“问题是否解决”。

因此找对资料仍会产生错误交互。需要区分说明、提问、上传要求与操作，只有实际操作才收集是否解决的反馈。固定测评策略的 not_solved 不是对问句的真实答案，不可据此补造噪声特征。

### T48：提供的知识缺少答案，咨询流程又把输出完成当成问答完成

补充 T8D04 型号后仍无绿灯解释。该型号对应 127 条官方 Q&A 无 whole-word green 命中；bp-0091 仅指向产品手册或 App 的 LED 说明。此前完整资料复核也未找到具体绿灯含义。本结论限于提供的 Q&A，不代表外部官方手册没有答案。

`conversation/product_questions.py:177` 只凭回复流 completed 把任务记为 answered，没有区分“给出答案”和“承认没有答案”。此次如实说明证据不足是正确的，但缺少后续可执行出口。应补可靠知识，或将无法回答的状态保留下来并给出可用的资料/人工路径。

## 验证边界

- 原始失败与重复结果见各 T*.json、followups/；来源和人工判据保留不变。
- cause-probes.json 保存五项离线机制验证；其中 T7/T56/T61 的人工构造输入用于控制单一变量，不伪称真实模型原始输出。
- 本轮只诊断和评审方案，没有实施修复，没有做“修复后通过”的结论。
