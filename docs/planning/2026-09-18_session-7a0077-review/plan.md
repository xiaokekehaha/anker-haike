# 基于服务目标的会话修改方案

## 1. 目标与范围

目标：用户每一轮都得到符合当前诉求、操作条件和真实服务能力的回应。可验证进展包括确认现象、获得影响下一步的答案、完成可执行操作、恢复功能、取得真实售后回执。

本方案覆盖会话 7a0077 暴露的问题：识别与回复脱节、不能操作仍机械推进、降级抹掉情绪、型号资料和步骤冲突、人工能力文案不准确。首先改诊断及其对话支路，复用已有意图理解、事实状态、NextAction、业务办理和事件持久化。

本文件是待实施设计，本轮只形成方案。实施开始后保持本文件不变，调整写 addendum.md。

## 2. 每轮的职责分工

处理顺序：输入解释 → 验证并更新事实/服务状态 → 决定本轮处理方式 → 现有业务能力执行 → 根据实际结果生成主回复 → 持久化并发布。

三个职责集中管理：

1. 用户当前需要什么：由现有 TurnInterpretation 和 turn_decision 表达，新增服务决策只处理继续、解释阻碍、暂停、提供选择等服务方式，不重复保存型号和故障事实。
2. 可以做哪个诊断操作：仍由 diagnose/decision.py 选择，再由 guide/steps.py 校验发布；服务决策传入用户意愿与资源约束。
3. 应该怎么说：由 conversation/reply.py 根据已确认事实、情绪依据、当前问题/步骤及实际执行结果组合回复。understand 不再提前发送一段独立的情绪文案。

每轮只有一份主回复计划；工具进度、证据、步骤卡、业务回执仍按原协议发布。这里的统一不是在事件出口丢弃第二条消息，也不是把所有图节点合并成一个大函数。

## 3. 改动 A：统一服务决策与回复

### A1. 服务决策模块

新增 orchestrator/app/conversation/service_policy.py。Interface 为 decide_service_turn(context) → ServiceDecision：接受类型明确的本轮解释、当前问题的服务状态和可用能力，返回可序列化结果；不调模型、不写库、不发消息。

ServiceDecision 的互斥种类为 continue_work、answer、ask_blocker、explain_step、offer_choices、pause。引用现有 input_id/issue_id/card_id 与原话依据，不复制全量会话。acknowledgement 记录需回应的具体经历来源，而非再次输出独立情绪等级。

先执行已有的设备风险限制和有效用户命令校验。纯情绪表达只改变回应及是否应提供选择，不自动执行转人工、不自动申请补偿、不自动废弃当前步骤。情绪与新的明确业务请求并存时，处理该请求并合并回应；“很生气，但继续帮我查”仍可继续有依据的排查。

### A2. 接入主流程

- sessions/graph.py 的 understand 保留解释、状态更新和进度事件，把 offer_human 的 say 文案改为 ServiceDecision 中的可用选项。
- route_entry 消费服务决策：ask_blocker/pause/offer_choices 走对应对话路径；continue_work 进入现有诊断或业务路径。
- conversation/reply.py 按本轮意图区分 complaint 与诊断 explain。owns_diagnostic_reply 只约束操作内容，不再把投诉统一转换成 explanation。
- clarify、dialogue、guide、summarize 等本次涉及的终点复用回复组合逻辑；各分支提供已有问题、步骤或摘要内容。每条诊断路径只选定一个主回复发布点。
- 消息继续通过 effects.py 的持久化与幂等机制发布，稳定 message_id 绑定 input_id 和主回复角色。进程恢复不重新生成另一条安抚消息。

### A3. 回复结构

有不满时：一句基于真实经历的承接 → 已确认现状 → 一个必要问题或明确选择。无新情绪证据时不每轮重复致歉。

步骤操作原文继续来自审核计划，回复生成不得增删操作参数。已有问诊题由结构化对象提供，情绪承接不能把同一题重新改造成另一个事实问题。即使不用模型润色，也应生成完整、相关的回复。

例：用户“我很不开心”，当前已经准备摘要。结果为 offer_choices，回复说明问题尚未解决和摘要已准备，给出“暂停排查/使用摘要联系现有客服渠道”等实际可用选择，不再输出无步骤模板。

## 4. 改动 B：无法操作后的处理与恢复

### B1. 将操作历史与执行事实分开

guide/verify.py 继续记录 solved/not_solved/cannot_do 原始反馈及来源；在诊断模块提供统一的可执行性和去重判断。真实已执行记录来自 solved/not_solved，cannot_do 表示当时未执行。steps_executed 可以在本次实现中改名为准确的 step_attempts，并同步相关内部消费者；外部历史原文及原始反馈不改写。

不能简单从去重集合移除所有 cannot_do，否则会立即循环下发同一步。为当前问题保存 StepBlocker：关联 card_id、plan_id、step_id、原因及原话、询问状态、是否解除。资源不足或明确拒绝仍阻止重复推荐；只有用户明确表示条件已变或要求重试，并通过当前资料/风险检查，才允许恢复。

StepBlocker、服务意愿和情绪状态加入 reduce.py 的 ISSUE_FIELDS，支持换问题、恢复问题和进程重启。历史 query/explain/complaint 均不能重复计数或解除阻碍。

### B2. 具体决策规则

| 输入或状态 | 下一步 |
|---|---|
| 第一次无法操作，原因未知，原因会改变后续路径 | 问一次阻碍原因；暂停自动推进 |
| 备注已说明没有工具/备用设备 | 不再追问同一原因；筛掉依赖这些资源的步骤 |
| 不清楚怎么做 | 解释当前已审核步骤，仍记为未执行；需要反馈卡时重新签发令牌 |
| 明确不愿继续或要求暂停 | 停止自动下发步骤，保存进度并说明可用出口 |
| 明确只想跳过当前步 | 记录 skip 意愿，检查后续步骤条件后再决定是否推进 |
| 阻碍仍未知且用户不愿回答/重复无法操作 | 提供暂停或售后记录选项，不继续累计追问 |
| 用户后来表示条件具备并明确继续 | 解除对应阻碍，重新校验并发布可执行步骤 |

guide/verify.py 的 cannot_do 不再直接按 next_on 推进，先返回重新评估。diagnose/decision.py 的 decide_next 在选择步骤前检查阻碍与用户意愿；guide/steps.py 发布前再次检查，防止旧游标绕过限制。

现有执行/跳过次数上限继续作为兜底；本次用具体反馈驱动提前减负，不把 executed+skipped 生硬合成情绪分数。用户已明确愿意继续时，应评估可执行方案，而不是仅因情绪等级终止服务。

### B3. 最小交互与后续控件

首版复用 StepFeedbackPayload.note 和聊天输入收集原因，避免改所有反馈请求。将 StepCard 的“做不到 / 跳过”含义在后续交互中澄清，不能仅凭旧按钮断定用户拒绝排查。

可选第二步：前端增加“缺工具/不会操作/先跳过/不想继续”的快捷选择，并允许不说明原因。若实现，新增独立结构化字段，不把故障观察 observations 借用为用户执行条件；修改 contracts/haike_contracts/actions.py 后 make contracts 生成产物并验证前端。

## 5. 改动 C：情绪观察与持续状态分开

### C1. 明确本轮证据

TurnInterpretation 的情绪观察允许 level=null，表示本轮没有足够情绪依据。明确的平静、感谢、不满等仍可给出等级和原话；缺失值不再默认 calm。运行器提供 source=model/rules/no_signal/unavailable，不能由模型自称调用成功。

emotion/policy.py 接收本轮观察及当前问题的 prior state：

- 有可信原话依据时更新当前等级；规则命中可以提高等级。
- no_signal/unavailable 保留已有状态，不新增“平静”样本，不计算 falling。
- 没有历史观察时保持未知；用户界面和分析显示“未判断”，不能伪装为平静。
- 有明确缓和证据可以更新为 calm，但不能把情绪标签下降当作设备已解决或满意度改善的证明。

reduce_turn 停止根据每轮默认值重建 emotion，更新入口集中到 emotion/policy.py。当前情绪状态及来源按问题持久化；不从另一设备问题继承诊断服务约束。

### C2. 协议和提示

contracts/haike_contracts/common.py 的 Emotion.level 支持未知（null），摘要和管理台对应显示“未判断”；运行日志区分本轮观察与沿用状态。修改 Pydantic 模型后运行 make contracts，随代码提交生成产物，不手工编辑生成文件。

config/emotion_policy.yaml 负责回应语气与可选服务方式，不能作为转人工/补偿的执行授权。无需扩大情绪种类或要求模型输出未经校准的置信度。

理解失败的本轮仍保留已确认产品、现象、待办和情绪。结构化模型输出错误要单独修复；不得通过接受无依据业务引用来绕过校验。

## 6. 改动 D：把型号和资源适用性落实到操作发布

### D1. A1289 的具体修复

核实已保存的官方原文及适用条件，新增 A1289 的 SKU 专用计划，引用对应官方资料锚点。更新 config/plans.yaml 与 config/fault_cards.yaml 的候选映射和版本。清理、换线和复位分别核对依据；不能只替换第三步文字而不检查适用条件。

已有通用 pb_port_debris 对 A1289 的适用性应明确限制。方案建议在 AppliesTo 增加 exclude_skus，给已知不适用的通用计划列出型号例外；SKU 专用计划覆盖其已验证场景，其他机型的通用计划维持按原条件适用。不要因为存在某个 SKU 计划就排除该型号所有通用维护计划。

### D2. 统一校验

- plans/models.py 声明步骤所需资源（如软刷、备用线、另一台设备）及计划型号限制。
- plans/library.py 的候选筛选实施型号限制；配置校验检查型号、证据及必要元数据是否完整。
- diagnose/decision.py 同时考虑症状、型号、已知观察和用户可用资源。
- guide/steps.py 在最终发布处复查 plan.applies、资源限制、来源及现有操作安全限制；不能因为本地证据缓存存在，就跳过型号核对。

资源未知不代表必须逐项问完。只在它影响下一步或用户反馈无法操作时确认。资料优先级必须结合型号和同一操作适用条件，不能仅按检索分数排序。

本期用明确适用范围和专用计划解决已知冲突；自动识别所有自然语言资料冲突是可选后续能力。

## 7. 改动 E：人工能力与状态文案一致

回复使用现有业务模块实际提供的能力与执行回执：只能生成摘要时写“已整理，可复制给客服”；提交能力存在但未执行时写“可申请”；有成功提交回执才写“已提交”，有接单状态才写“已接单”。状态先区分，文案再映射。

有真实人工审核能力的业务案件继续正常运行。单纯 complaint 不自动创建补偿承诺；用户明确提出补偿时记录诉求，是否能评估或执行由现有政策及业务权限决定。没有核实的客服入口不编造链接。

escalation/summary.py 主问题优先列用户已确认现象，假设单列；“未执行/执行无效/无法继续”保持区别。生成摘要之后仍允许用户主动恢复可执行的排查。

## 8. 文件与职责

| 文件或模块 | 变更 |
|---|---|
| conversation/service_policy.py（新增） | 类型明确的本轮服务方式决策，集中用户意愿、阻碍和真实能力判断 |
| conversation/interpret.py、reduce.py | 提取并验证情绪/执行阻碍；按问题保存新状态；去除默认值覆盖 |
| emotion/policy.py、config/emotion_policy.yaml | 无信号与识别失败保持状态，输出有依据的策略 |
| sessions/graph.py、conversation/reply.py | 接入决策，拆开投诉与诊断解释，组合一次主回复并复用持久化 |
| guide/verify.py、diagnose/decision.py、guide/steps.py | 反馈记账、可执行性判断、阻碍后的恢复、步骤发布校验 |
| plans/models.py、plans/library.py、config/plans.yaml、config/fault_cards.yaml | 型号范围、必要资源、A1289 专用计划及引用 |
| escalation/summary.py、相关展示处 | 正确描述未执行、未知情绪、摘要与真实人工状态 |
| contracts/haike_contracts/common.py 及生成产物 | 情绪未知状态；可选快捷原因控件另改 actions.py |

新增内部类型用 dataclass/Pydantic 明确字段，顶层导入，不新增 Any/noqa。已有历史记录不重写，旧会话继续可读是历史观测要求；不为旧内部实现维护双写和双路由。

## 9. 验收与测试

以原始 7 条用户文本和反馈为基线输入构造离线场景，但新系统询问阻碍时，测试应提供对应回答，不盲目向已经不存在的旧卡片继续点击。

必须验证：

1. “难用”首轮承接不满并问具体问题；没有凭空添加已确认故障。
2. schema 错误/超时/纯“没有”不产生情绪缓和记录，已知事实与待办保留。
3. “我很暴躁/我很不开心/产品太烂”在问诊、步骤等待、摘要已准备三个阶段均正确回应；不夹带无关诊断模板，不触发未经要求的转接或补偿。
4. “生气但继续查”仍推进适用诊断；“不想继续”停止自动发步骤；恢复请求可继续。
5. cannot_do 的原因只问必要一次；没有工具时不再发依赖该工具的步骤；条件改变后可重新发布，不能双计反馈。
6. 单纯投诉或解释不消费 pending_card；恢复步骤使用新卡片令牌，旧令牌失效。
7. 已确认 A1289 时不会发布不适用的通用复位；专用计划不能泄漏给其他型号；未确认型号不猜选专用操作。
8. 主回复、卡片、摘要在重试和进程恢复后完整且不重复；真实业务回执不能被统一回复误删。
9. 只有用户确认恢复或真实业务结果才进入对应完成状态；未知情绪不算缓和，摘要不算接单。

测试落点：新增 test_conversation_service_policy.py、test_conversation_service_flow.py；按改动补充现有 test_l3_experience.py、test_guide.py、test_diagnostic_next_action.py、test_plans.py、test_conversation_diagnostic.py、test_conversation_escalation_summary.py、test_conversation_recovery.py。修改前完整读取测试文件；更新旧行为断言时保留其原有安全、去重和执行边界验证。

模型使用 FakeChatModel，知识库使用 tests/fake_weknora.py，HTTP 会话用 tests/conversation_runtime.py；禁止真实模型/知识库调用。断言用户可见行为和状态不变量，不逐字锁定所有安抚文案。

实施后运行 make lint、实际新增/修改及直接相关测试文件。涉及协议运行 make contracts 和 make contracts-test，检查生成产物并执行前端 typecheck；涉及前端交互再运行对应测试。用户要求提交时，按项目约定先 make up，再 scripts/ci-local.sh；本方案阶段不运行构建或全量测试。

## 10. 实施顺序

1. A + C + E：先完成服务决策、回复一致性、可靠情绪状态及真实能力文案；这是同一条用户可见链路。
2. B：完成阻碍状态、cannot_do 分流、恢复与去重。不能只添加一句“为什么做不到”而不消费答案。
3. D：完成 A1289 专用计划与最终发布校验；可在前两项期间独立准备资料核验，交付前必须完成。
4. 运行端到端离线场景及相关检查。快捷原因控件、性能优化、跨资料自动冲突检测另行迭代，不作为此次修复前提。
