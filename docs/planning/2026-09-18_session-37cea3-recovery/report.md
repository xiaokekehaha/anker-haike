# 会话 37cea3：回退与恢复机制分析

分析日期：2026-09-18。对象：[七轮会话](http://localhost:8000/admin/sessions/37cea3ff86574d05a162adf53bca34d3)。本轮为只读业务分析，未修改实现、未向原会话发送消息。

## 结论

系统已有暂停恢复、事实纠正、切换问题和摘要后重新排查等局部能力，但缺少贯通交互与业务决策的纠错流程。用户补充情况后，流程可以重新运行，却仍可能被旧分类限制，重复到达相同出口。本次就是可复现的候选过滤缺陷，不能归因于用户表达不规范或真实知识缺失。

## 会话追踪

| 轮次 | 用户输入 / 变化 | 实际处理 | 问题 |
|---|---|---|---|
| 1–3 | A1289 难用；有输出；给自身充电很慢 | 写入症状码 pb_no_input，检索后询问连接设备时的屏幕状态 | 后续输入/输出场景需要能够重新核对 |
| 4 | 设备不在身边 | 记录 device=false，暂停操作 | 此次暂停本身合理 |
| 5 | 连接笔记本时显示 UVP／屏幕显示异常 | 记录单一观察 laptop_uvp，继续追问设备是否到手 | 两个现象被压成一个；回复未说明已记下什么、与前面描述有何关系 |
| 6 | 已在 | 记录 device=true，重新决策，输出无适用路径摘要 | 条件恢复成功，路径选择失败 |
| 7 | 再次输入 UVP／屏幕异常 | 确实重新检索，再次生成相同原因的摘要 | 没有回到需要核对的分类与观察 |

最终 steps_executed、step_attempts、exhausted_plans 均为空。问题保持 open，人工状态为 prepared（摘要已整理，尚未接入人工）。

## 直接原因：旧分类挡住了新观察对应的路径

症状码是系统对现象的分类。本次只保留 pb_no_input，表示充电宝自身输入充电问题。

1. 真实状态已有 pb_737_display=laptop_uvp。
2. 计划库已有 pb_737_laptop_uvp，型号匹配 A1289，观察条件也满足。
3. 该计划的症状码为 pb_no_output、pb_indicator_abnormal、pb_port_damage，不含 pb_no_input。
4. decide_next 的观察候选仍先按旧症状码过滤，因此 UVP 计划没有入选。
5. 剩余 pb_737_output_check 和 pb_737_display_reset 均被 laptop_uvp 观察排除。
6. 最终返回 handoff_offer / knowledge_coverage_missing。

证据位置：[观察候选过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/decision.py:510)、[计划库症状过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/plans/library.py:120)、[UVP 计划](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/plans.yaml:301)。

这不表示收到 UVP 就应直接执行该计划。当前同时涉及自身充电慢与连接笔记本的现象，正确行为可以是回到场景澄清；现有实现直接宣布资料缺失，掩盖了候选选择冲突。

## 回退能力的实际边界

| 能力 | 当前情况 |
|---|---|
| 暂停后继续、设备到手后恢复 | 已实现；本次“已在”被正确接收 |
| 纠正已记录事实 | 已有 corrections 路径，保留原记录并写替代事实；自然语言识别须给出明确纠正及事实 ID |
| 新问题与返回旧问题 | 已有 new_issue / resume_issue，问题切换会挂起卡片，返回时签发新卡片身份 |
| 人工摘要后继续排查 | 可重入；第 7 轮运行轨迹证明已重新检索 |
| 明确修改上次回答、改选历史观察 | 用户界面未提供入口；answered 观察不再按普通待答问题匹配 |
| 历史步骤反馈撤销 / 修改 | 当前动作契约未提供统一操作；历史已反馈步骤只展示结果 |
| 摘要页直接恢复排查 | 当前摘要卡仅提供复制，用户须自行输入恢复或纠正意图 |

相关实现：[动作契约](/Users/xiaoke.zhou/Documents/workspace/anker-haike/contracts/haike_contracts/actions.py:9)、[事实纠正与问题切换](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/conversation/reduce.py:85)、[观察待答范围](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/conversation/reduce.py:547)、[问题切换入口](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/Timeline.tsx:37)、[历史步骤呈现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/StepCard.tsx:36)、[摘要卡入口](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/SummaryCard.tsx:65)。

这里核查的是该会话涉及的排障与摘要流程；没有对退款、换货、发货等业务做完整逆向流程审计。

## 另外两处放大问题的设计

- 多现象被强行单选：match_reply 同时命中不同观察选项时，按命中文本长度择一。本次原话确定返回 laptop_uvp，屏幕异常没有独立进入结构化观察。应澄清“是 UVP、屏幕显示异常，还是两者都有”，并保留用户原话。[匹配实现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/observations.py:194)
- 原因展示失真：管理端把所有 R2 固定显示为“适用步骤已耗尽”，本次实际零步骤，底层原因却是 knowledge_coverage_missing。需要展示具体结束原因，而不是只映射兼容规则码。[管理端文案](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/admin/format.ts:38)

## 建议的改动顺序

1. **先修候选重评。** 新观察与旧分类不一致时重新核对场景，或纳入满足型号、观察、资源和风险条件的已有计划。禁止把旧分类过滤后的空集合直接解释为知识缺失。保留“自身充电慢”原记录，不为让 UVP 路径通过而强改历史。
2. **建立明确的纠错动作。** 提供“修改刚才回答”“重新选择现象”“暂停 / 继续排查”；动作绑定要纠正的记录，更新后使依赖该记录的分类、计划和待办失效，再生成下一步。旧事实和实际执行历史继续保留。
3. **改进停滞出口。** 候选冲突时给出一条具体澄清；摘要卡提供“补充情况继续排查”和“修改记录”。相同状态重复输入时解释当前缺口，避免重复生成相同摘要。
4. **补组合场景回归。** 至少覆盖自身充电慢后补 UVP、一次报告多个观察、设备不在→补充观察→设备到手、已回答后改选、摘要后纠正并恢复。

前两项是本次问题必需的修复。完整的历史版本回溯界面属于可选复杂度。后续若扩展到已发生的退款或发货，应通过对应取消/补偿流程处理，不能把界面返回等同于外部业务撤销。

本次更合理的回应应是：“已记下设备在身边。你前面提到给充电宝自身充电慢，现在又提到连接笔记本时 UVP 和屏幕异常。这两个现象都存在吗？我们先确认当前要排查的场景。”

## 验证

只读取得真实 checkpoint，在本机调用纯函数 decide_next；未调用真实模型、知识库或修改会话。

执行 `cd orchestrator && uv run --env-file ../.env python /tmp/haike_37cea3_probe.py` 的结果（临时文件在完成后删除）：

```text
actual: handoff_offer knowledge_coverage_missing
mixed_answer: laptop_uvp
UVP plan: ['pb_no_output', 'pb_indicator_abnormal', 'pb_port_damage'] ('ok', [])
eligible: ['pb_737_output_check', 'pb_737_display_reset']
only_add_UVP_candidate: step ranked_plan pb_737_laptop_uvp / s1
AssertionError: RED: an applicable UVP plan exists, but candidate selection reports knowledge_coverage_missing
```

对照仅在内存把已有 UVP 计划加入 plans_ranked，其他状态不变，即可产生步骤决策。这证明候选入口存在缺口，不代表已经完成生产修复或验证完整发布链路。

已有测试执行：

```text
cd orchestrator && uv run pytest -q tests/test_conversation_operation_conditions.py tests/test_conversation_reduce.py tests/test_conversation_lifecycle.py tests/test_conversation_pending_flow.py
34 passed in 3.17s
```

已有测试通过与专项断言失败同时成立：基础恢复能力存在，但未覆盖本次场景组合。业务实现尚未修改，缺陷仍可复现。
