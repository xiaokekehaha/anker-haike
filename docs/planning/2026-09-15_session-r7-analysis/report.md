# 会话 2702fe9bdd4942e9ab84122d42a6848e：R7 原因与机制评价

## 结论

此次 R7 不合理。用户两次「不能」均被识别并成功应用，第二次回答已将症状判别候选缩小为「不充电」。问题出在状态合并与澄清判定不一致，不能归因为用户回答不清楚，也不应简单增加追问次数。

本次为分析：没有修改业务代码、会话状态或部署服务。数据库仅通过 LangGraph saver 读取本会话 checkpoint。

## 实际对话（北京时间 2026-09-15 10:57）

| 轮次 | 输入/追问 | 系统内部结果 |
| --- | --- | --- |
| 1 | 用户：eufy X10 Pro Omni，启动不了；助手：设备按电源后能正常启动吗？ | 模型已提取 power_failure，产品最终 confirmed_sku，仍进入症状追问 |
| 2 | 用户：不能；助手：放回基站后有正常充电指示或语音吗？ | no 有效应用，8 个候选变成「不开机、不充电」，attempts=2 |
| 3 | 用户：不能；助手：整理摘要交人工 | no 有效应用，候选只剩「不充电」，却触发 R7 |
| 4 | 用户：还有其他的方案吗 | 走 explain → dialogue，助手直接给出检查基站供电、触点、重新放置等建议，没有进入步骤卡流程 |

完整必要证据见 evidence.json，复现结果见 repro-result.json。

## 根因链

### 1. 已有结构化症状，却又被旧的文本兜底判断否决

首轮模型提取并持久化 `symptom_codes=[power_failure]`。但 `clarify.decide` 的症状判断仍依赖 `_has_symptom_text`，没有直接承认已确认的结构化编码。

实际测试：`启动不了` 返回 false，`无法启动` 返回 true。前者未包含在旧关键词中，且长度小于 6。因此出现用户已经说「启动不了」，系统又问「能正常启动吗」。

位置：orchestrator/app/sessions/clarify.py:215、:225、:304。

### 2. 有效问答的收敛状态被历史编码覆盖——此次 R7 的直接原因

- `interview_answer` 正确消费第二次 no，返回 `candidates=[不充电], status=narrowed`。
- `reduce_turn` 随后扫描所有仍有效的旧事实，发现首轮已有 power_failure，便将 interview.status 无条件改为 superseded；这轮并没有新增或纠正症状。
- `decide` 因而没有进入 narrowed → continue 分支；原文「不能」和旧症状「启动不了」又未通过文本兜底判断。
- 再次请求 symptom 澄清时，attempts 已达 2，于是 R7，同时把 interview 标为 insufficient。

因此 checkpoint 出现自相矛盾的组合：候选已经只剩「不充电」，状态却是 insufficient。

位置：orchestrator/app/conversation/reduce.py:295；orchestrator/app/sessions/clarify.py:220、:245、:256。

### 3. R7 文案混淆不同原因

R7 被用于 product / symptom / conflict 三种澄清，摘要原因却固定成「产品品类无法确认」。本会话产品已经 confirmed_sku，这条原因明显错误。

位置：orchestrator/app/escalation/summary.py 的 REASON_TEXT[R7]。

## 离线可重复验证

```sh
orchestrator/.venv/bin/python docs/planning/2026-09-15_session-r7-analysis/repro.py docs/planning/2026-09-15_session-r7-analysis/repro-input.json
```

脚本从原会话第二次回答前的 checkpoint 提取最小所需状态，执行真实 `symptom_question_answer → reduce_turn → decide`。不调用模型、不写数据库。

输出：回答被接受；问答计算结果 narrowed；reduce 后 superseded；最终 R7。断言「已收敛不得 R7」失败，退出码 1 为预期的 bug 复现。

单变量对照：仅把 reduce 后的 interview.status 改回 narrowed，其他状态包括 attempts=2 不变，decide 即返回 continue、charging_failure。证明主因是收敛状态被覆盖，而不是必须放宽两次上限。

## 机制是否合理

| 机制 | 评价 |
| --- | --- |
| 限制无效澄清、防止反复追问 | 合理，但必须先判断回答是否已提供足够信息。总提问次数不能直接代表失败次数。 |
| 用当前问题解释「不能/没有」 | 合理，本会话已正确绑定问题并消费，不能再要求用户把问题复述一遍。 |
| 结构化问答缩小排查方向 | 合理，但方向不是已确认硬件根因；「不开机」和「不充电」也可能同时存在，不能因分类而删除原始事实。 |
| 历史症状编码无条件覆盖本轮问答 | 不合理，已有事实不能自动作废新回答。 |
| 产品/症状/冲突共用 R7 固定产品文案 | 不合理，会向用户和运营报告错误原因。 |
| 正式流程停止后，自由对话又发操作建议 | 边界不一致。第四轮还将原因推断到内部电池/主板，但本会话没有检索或执行验证来支持该判断。建议只能来自受控方案，继续排查应回到步骤流程。 |

## 奥卡姆剃刀下的建议顺序

1. 先修一致性：已有有效症状编码应被澄清层认可；历史编码不应把本轮有效问答的 asking/narrowed 状态改成 superseded。只在明确新增/纠正信息取代旧问答时才替代。
2. 保留既有追问上限，先验收「有效回答完成收敛时即使 attempts=2 也继续」。此处不需要先增加轮数、新模型或复杂评分。
3. 摘要使用实际原因：症状待补充、型号不明、信息冲突分别描述；若没有对应计划，则报告计划缺失。
4. 根据产品范围补齐不开机/不充电的经过审核的基础方案，并让“还有其他方案吗”复用受控排障流程。

## 修正 R7 后还有能力缺口

已在当前运行容器内只读验证：`allowed_for(..., symptom_codes=[power_failure])` 和 `[charging_failure]` 均返回空列表。

因此修复此次误判后，同样的问题可能正确进入 R5「当前产品的这一问题没有可用的排障计划」。这属于方案覆盖不足，不是用户描述不清。不能承诺只改 R7 就能完成自动排障，也不能借用不相关的吸力下降方案凑步骤。

## 测试遗漏

现有 `test_symptom_interview_narrows_or_stops_after_two_questions` 的首轮是「坏了」，测试解释器没有产生任何症状事实，故没有覆盖「旧 power_failure 编码 + 两轮有效判别」的组合。它能验证无旧事实时的 no/no 路径，不能防住本次覆盖问题。
