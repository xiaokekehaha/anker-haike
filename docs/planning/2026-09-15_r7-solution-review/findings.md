# 发现

- 当前 reducer 调用 diagnose.decision.accept_answer，已移除 spec 引用的无条件 superseded 覆盖逻辑。
- decide_symptoms 采纳事实编码与已接受问答；词面匹配仅作为正向证据。
- 已实现候选对应相同非空计划集合时继续，以及连续 unknown 答案停止；尚不是完整的行动层进展度量。
- R7 摘要按 clarification.reason / diagnostic_decision.reason 渲染，问答进入 observations；hypotheses 仍仅来自 plans_ranked。
- 既有 diagnostic-first-principles 目录记录过全量测试与部署，本次将独立运行局部回归，不把历史记录当成本次环境验证。
- 本次局部回归 25 项通过；原 R7 形状在当前实现返回 continue，不能再把 spec 当成未修复缺陷清单。
- 当前同动作判定要求各候选计划集合完全相等；可研究共同可执行步骤，但必须同时核对步骤前置条件、风险限制和已执行记录。
- 症状编码 power_failure 与 charging_failure 可以并存；候选集唯一也只代表当前分类配置收敛，不能证明硬件根因。

## 开发确认
- 只放宽澄清层的计划交集不足以保证行为正确，必须将同一计划/版本约束贯穿故障卡、排序和操作发布。
- 原有无知识适配器路径传入 exhausted_plans，正常检索路径遗漏；本次统一传入，防止重新选中耗尽计划。
- 内存测试 fixture 默认替换了解释器，完整问诊测试需显式调用真实 symptom_question_answer 来保留确定性答案解析。
- 无法解析回答必须在 reducer 的诊断路由中继续，不能因 primary_intent=unknown 落入普通闲聊而绕过预算。
