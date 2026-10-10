# 开发记录

## 第 1 轮

继承上一阶段 R1–R5 实现，在新分支修复巡检与检索测试夹具。设计与红绿记录见 addendum.md。完整 CI：后端 993 passed / 2 skipped，契约 90 passed，前端 229 passed，构建成功。真实 63 单版本、原文、附件校验有效，结论见 round-01/review.md。

## 第 2 轮：R6.1

先完成 round-02-design.md，随后修改：

- `official/qa_index.py`：单段、编号、重启后售后使用相同类型构造入口；所有 Guide 保留节点。描述设备行为或可能原因的动词不直接算操作；有明确操作请求则保持 action。
- `plans/qa.py`：只消费有类型的节点，不把 answer 重新包装成默认 action；保留原段落 ID 与分支。
- `guide/steps.py`：保留纯说明和尾部说明，返回解释文本和来源；纯说明终点与排障耗尽分开。
- `sessions/graph.py`：说明用普通消息展示；纯说明只完成答复，沿现有队列推进，不执行 close 的故障解决模板。
- `diagnose/decision.py`：后续回顾明确“已提供解释”不等于设备已修复。

验证：新增 test_knowledge_explanations.py 覆盖通用语言结构、官方回归、纯说明 HTTP 链路、尾部保留及统计语义。首轮 79/80，通过修正无效比例断言后扩大回归 230/231；剩余失败为 T28 旧测试要求对硬件结论再次反馈，已按需求更新。最终相关 11 文件 **231 passed**。make lint、diff 检查通过，完整 CI 执行中。

完整 CI 已完成：后端 **1008 passed / 2 skipped**，契约 **90 passed**，前端 **229 passed**。make up 更新本地服务后启动 round-02 全量采证；采证期间冻结生产代码。

范围：R6.1 不等于 R6 完成。混合段落拆分、索引元数据排除仍待 R6.2；R7/R8/R9 尚未开发。不改官方源数据，没有 QA 或 T 编号的生产分支。

## 第 3 轮：R6.1e–f

先记录 round-03-design.md，再把祈使副词、You can/should 等客户操作请求、recommended to 等建议统一纳入指令语法。动作词复用同一集合；首次回归 189 passed / 1 failed，发现 power 作为名词标题也被匹配，进一步限制为 power on/off/up/down/cycle 的动词结构。问题内新增已展示知识节点记录，避免把说明重复附到每张卡；该记录不进入用户操作历史。

第二轮真实采证 63/63 有效，逐案复核完成；T16/T22/T32 的新回归已记录，未隐瞒为改善。只读 checkpoint 补核确认：第一轮 T29 过度跳过 s3 是 R8；第二轮 T29/T39/T41 泛问来源为 R3 fallback 的 uncertain。T49 排障任务未丢，T59 跨型号请求原文未丢。

第三轮验证：7 文件 190 passed，加入 HTTP 跨轮持久化后扩大为 11 文件 **242 passed**。HTTP 测试一次因可选 context 字段省略而 KeyError，改为按可选字段读取后通过；未更改实现来伪造空字段。make lint 与 diff 检查通过，本地构建完成，round-03 全量采证开始。

## 第 4 轮：R6.2a–d

先完成 round-04-design.md 和 addendum.md 的图路由补充，再实现 FaultSection 的原始段落范围、多个明确故障小节的选择入口与互斥终点。普通阶段标题不推断为替代故障；已有审核分支保持优先。Plan.next_step_id 统一处理选项，decide_next 沿回答历史走图，prepare_step 跳过已答节点时也保留分支。非操作节点无设备资源要求，合成选择节点不误附整篇图片。仅过滤独立索引字段行，源 QA 不改。

新增 test_knowledge_branches.py：两个分支互斥、暂停后重放、发布器从入口重放、通用合成文档、阶段型反例、元数据与两个真实 HTTP 选择路径。相关 5 文件 **97 passed**；make lint 与 diff 检查通过；完整 make ci-local 全绿。本地构建后进行第四轮 63 单采证。

## 第 5 轮：R8 完整覆盖

按 round-05-design.md 实现词边界、明确对象、肯定来源和整卡覆盖；移除 new/full 及可能作名词的 cleaning 等形式作为已完成动作证据。额外 inspect/remove 等未覆盖动作、问句或材料请求都会阻止整卡跳过。已有 instruction_src 执行反馈去重不改。

原 test_guide_step_kinds 的 T36 夹具要求“cleaned everything”直接跳到 s6，正是在固化未知对象通配行为；更新为 s2 保留，并断言没有错误跳过。test_reported_action_coverage.py 覆盖模糊对象、名词误匹配、多动作/多对象、事实极性/来源、明确同义触点及问题隔离。首轮相关 7 文件 179 passed；审查补充 cleaning task 报告反例后再次执行相关回归。保守边界会留下部分重复操作，这一限制已在设计中明确。

第 5 轮最终相关 **183 passed**，63 单采证有效、逐案复核完成；没有将 T29 的停在问句算作操作路径通过。

## 第 6 轮：R3.2

按 round-06-design.md，intake 缺失结构化症状时用单次专用事实 schema 补抽，输入上下文仅本轮原文，无候选知识。引文越界或非症状输出不接收；失败不改变原解释结果。reduce 将原始字段存为 unparsed_problem，后续合法症状到来后标记 interpreted，保留原来源；query 能在补充型号后继续使用尚未解析的原文；缺失语义事实不能据此发操作卡。

新增 test_problem_description_recovery.py，覆盖多语言字段、动作误抽、越界引文、空输出、失败有界、极性保持、错误码/纠正/其他意图不补抽、补型号后召回来源及 HTTP 两次模型调用后再检索。相关 4 文件 **118 passed**。lint 初次指出测试未使用变量，改为断言解释结果保持不变后清零。完整 CI 正在运行。

完整 CI 已通过：后端 **1081 passed / 2 skipped**，契约 **90 passed**，前端 **229 passed**。随后增加补抽 model_trace 以支持实际触发统计；审查发现公共 quoted 支持丢掉首/尾词，这不适合新增事实恢复边界，因此补抽使用仅空白/撇号规范化的严格包含校验，并加入 Never 前缀不得被丢弃的反例。最终相关 **119 passed**，lint 与 diff 检查通过；已重新构建以保证这两项补充进入第六轮实测版本。

## 第 7 轮：R7 请求证据

按 round-07-design.md 增加 request_quotes 协议、当前原话/字段/独立性校验，并在业务优先级排序后统一过滤额外查询。队列保存短请求引文，同时保留完整原文和原有业务对象绑定。明确的办理或排障替代请求可恢复诊断，单纯故障背景和明确拒绝不恢复。

备用路径纠偏、旧夹具补证、HTTP 夹具启用业务服务和固定提示容量基线的红绿过程见 addendum.md。最终相关 6 文件 **152 passed**；新增请求证据文件 14 项覆盖语义来源和真实 HTTP 入口。make lint 与 diff 检查通过，完整 CI 重跑中。

第 7 轮完整 CI 后端 1096 / 契约 90 / 前端 229 全绿，随后 63 单完成并逐案复核。已记录 T2/T6/T53 等剩余误读，不把采证有效当全部通过。

## 第 8 轮：R9 与 R2.1

先写 round-08-design.md。修正 classify、episode 和共用 SQL 的 closed_unresolved 投影，摘要保持 escalated，不再隐含真人参与。人工事件对任意案件状态都可证明 human_involved。终结时间、指标分母和管理端标签同步；无案件原始证据的历史错误标签不自动猜测回填。投诉和摘要模板移除“人工未接入”全局断言，以提交记录区别已整理/已排队。

新增 test_outcome_boundaries.py，覆盖过时咨询/结束语优先级、分母、真实 Postgres 四种状态投影、文案边界。后端相关 7 文件 **147 passed**，lint 通过。前端初次 25 passed / 1 failed 是旧常量测试固定截取前四个状态；新增结果后改为检验原状态相对顺序，并新增未解决关闭/等待人工的实际渲染测试，保留文字与色彩的断言。

第八轮最终前端相关 **27 passed**，63 单采证与逐项对比完成。T58 实际命中修改后的投诉模板，旧能力断言消失。T53 的真实 SQL 投影为 closed_unresolved、human_involved=false。T41 暴露前提错配，记录为待评审的知识适用性问题。

## 第 9 轮：R7e–f 与 R6.3

先写 round-09-design.md，再给额外订单/保修查询增加具体字段要求；队列保存原问题的字段、引文及作用域，自动推进和显式恢复均保留，避免恢复为默认订单信息。诊断求助与症状允许来自同条消息的不同句子，并统一相互冲突的 schema/提示定义。无需新的模型调用。

知识节点新增内部 source_gap 标记，仅识别明确悬空引用；正常 URL、后续正文、纯说明均保留。运行到缺口时展示已知内容和缺失说明，保留来源，走 R5 知识不足路径，不计已操作，不标咨询完整。新增 test_knowledge_source_gaps.py；原 rv-0371“完整说明”测试移入新的缺口回归，不放宽验收。

相关 8 文件 **182 passed**，lint 与 diff 检查通过。完整 CI 后端 **1121 passed / 2 skipped**，契约 **90 passed**，前端 **230 passed**。随后复查显式 resume_task 会再次校验旧引文，补上从已验证任务恢复原 AnswerRequest，并加入实际 understand/reduce 测试；最终请求与缺口两文件 **30 passed**。更新本地镜像，准备第九轮真实复测。

## 第 10 轮：最终验证

不再修改生产代码。最后显式任务恢复改动已包含在最终 ci-final.log：后端 **1121 passed / 2 skipped**、契约 **90 passed**、前端 **230 passed**，构建完成。第九、十轮各 63 单同生产版本采证完成并逐案复核。

最终工具复核发现摘要未展示 media，已补展示和比较字段并重跑全部差异。完整源文/事件确认 T40 的 rv-0073 有链接；没有为错误复核结论新增产品补丁。T23 风险误判、T35/T53 终点粒度新证据写入 next-phase-design.md 的 K8/K9，尚未实现，不计修复完成。
