# 现状与证据

## 已确认的业务事实

- T26：S1 Pro / T2080A，20972035 / E23，机器人清水水位异常、任务结束；没有图片。
- 本地官方条目 data/official/qa.yaml 的 rv-0063 共三段：翻转摇动、检查镜片、清洁液使用史 + 泡沫观察 + 有泡沫时排水换水试运行。
- 最新会话第三段整体被作为 action，只有操作结果反馈；测试器传入 not_solved 后转入购买材料收集。
- 模拟 not_solved 不证明用户回答了使用史、观察到泡沫或执行过排水。

## 证据

- data/official/tickets.yaml:469。
- data/official/qa.yaml:1343。
- docs/planning/2026-10-10-1550_official-63-latest-review/conversations/T26.md（已完整阅读）。

## 待核对

- 问句类型、选择项、答案持久化是否已有能力。
- 条件分支是否只存在于静态 action 模型，还是能驱动实际运行。
- 修改知识表示时如何保留源段落、图片、编号和顺序。
- 排障未完成时，售后入口如何防止提前推进。

## 首轮代码发现

- plans/models.py 已有 action/question/statement/material_request/handoff、options、branches、condition；next_step_id 能按问题选项选边。
- plans/qa.py 的 plan_of 按 guide.steps 一段生成一个 PlanStep；step_condition 只匹配段首 If 条件。T26 第三段先写使用史，内部 If foam is present 不会成为 condition。
- action 的 cannot_do 默认指向下一步；该行为不能用来证明条件动作已完成。
- 序号用于 instruction_src、步骤 ID 和卡片 ID；拆成多个节点必须保留原文位置另加稳定节点标识，否则历史去重和媒体定位可能受影响。
- 搜索发现契约、前端和运行时已经存在 answer 通道，需完整阅读后决定复用范围。

## 完整读取后的接口缺口

- common 契约待核对；actions/events 契约、StepCard.tsx 和对应测试已完整读取：question 已支持 options 和 text。
- guide/verify.py：问题的非选项短答直接走 next_on.not_solved；不能直接将含条件的问题挂上默认排水边。明确不确定也必须等待澄清，而非靠默认边推进。
- guide/verify.py：cannot_do 实际返回 reassess，记录操作阻碍；不是直接走 plans/qa.py 写出的 cannot_do 边。前述 cannot_do 默认下一步是静态模型行为，实际执行以 verify 为准。
- guide/steps.py：answered_history 按 instruction_src 去重；不同语义节点不可共用同一个证据 key。step_media 通过 s<number> 下标回找原段媒体，拆分后要改为显式来源绑定。
- StepCard.tsx 对 question 不显示 instruction，只显示标题；将“摇动水箱后观察泡沫”改成 question 时必须保留操作正文，不能让标题截断掉必要指示。
- 未回答/无法观察、非结构化短答的解析和分支，是需要补齐的行为，不应仅增加三张卡。

## 条件检查与现有覆写

- qa_index.py、operation_conditions.py、qa_overrides.yaml 已完整读取。
- qa_overrides.yaml 已有按来源条目 + 原段位置审核 kind/options/branches 的机制；可扩展为一个原段多个节点，运行时仍使用统一 Plan。
- answered_history 当前把所有非 action 尝试当成已消费，未知答案必须与已完成答案区分，否则 prepare_step 会跳过待澄清节点。
- fact_check.py 允许问题回答 text 不匹配选项时仍记 answered；对关键条件需要收窄为明确选项，防止事实预填绕过严格路由。
- fact_check.py 的条件跳过会保留最后一个动作以免耗尽；不能依赖这一启发式保证“无泡沫不排水”。T26 应用明确回答边与结构化门槛。
- 源条目中的“是否加第三方清洁液”是背景信息，不是排水门槛；“有泡沫”才是必要门槛。

## 会话集成与既有规划

- common.py 已完整读取；StepAnswer 为 option/text/unavailable，TroubleshootStep 无问答策略字段。可保留当前动作种类，但需增加前端可见的关键问题策略。
- graph.py 只定位并完整读取相关 await_input、反馈应用、卡片答案记录与反馈路由函数；尚未完整读取 3248 行文件。本轮不编辑此文件，实施前必须按 AGENTS.md 完整读文件。
- graph.py 的 route_after_apply 当前将 next 之外的大多数 verify outcome 路由到 close；新增“等待澄清”必须显式路由，不能仅给 VerifyOutcome 加枚举。
- 卡片答案同时写 card_results 与 issue.facts；未知答案不能让前端把当前卡折叠成已答，等待状态需覆盖这两个投影。
- 已有 2026-10-09 第二批步骤类型规格明确问题卡“选项 + 短答”；保留短答能力，以收窄解析、待澄清保证分支，不直接取消输入。
- 2026-10-10 K1–K9 规格已规划全库模型编译；本方案先完成“审核节点 → 现有 Plan”的必要通用能力，作为该阶段可复用的一部分。全库离线模型提取和其他根因不纳入本轮实施范围。

## 最终方案核对

- 必须区分“异常后重评”与“适用检查耗尽”；当前 Plan 只有 DONE/EXHAUSTED，实施补显式 REASSESS，并同步即时反馈/重放/发布。
- QAIndex.version 当前只跟 qa.yaml；Plan.version 固定为 1。拆分方案必须纳入覆写摘要和更新计划版本，旧混合步骤反馈不能证明新节点答案。
- 观察型 question 需要 device 资源；不能照搬普通背景问句的空 required_resources。
- 背景使用史未知可记录后继续，控制泡沫未知必须等待；细化前轮“所有未知都澄清”的建议，避免无关信息阻塞适用排障。
