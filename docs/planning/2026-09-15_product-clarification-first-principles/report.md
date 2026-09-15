# 会话 9db433aece2d47378f9ce8bbeb0701e4：R7 与「两句话到人工」的第一性原理分析

日期：2026-09-15。本篇只诊断，未修改代码、会话或部署。

## 结论

这次 R7 不合理。系统在**已经知道症状（运行异响）、已经拿到两张设备照片、用户也给了型号串（x00001）**的情况下终止会话，
理由写成「产品型号或品类仍未确认」。而目录里在范围内的品类只有扫地机器人一个，且它有覆盖异响的通用计划——
**型号从头到尾不是排障的必要条件**。

错的不是追问次数，也不是模型能力，是三条设计倒置：

1. 用「信息完备度」当推进条件，而不是用「有没有一个适用且安全的下一步」。
2. 唯一能降低产品不确定性的输入（照片），被排在需要它的判断（产品识别）之后。
3. 追问预算的计数对象（reason）与消耗预算的行为（模型自由生成的问题）不是同一件事。

## 一、实际发生了什么

42 秒，4 轮。

| 轮 | 用户 | 系统回复 | 内部状态 |
| --- | --- | --- | --- |
| 1 | 只有一张设备照片，无文字 | 「用户输入为空，无法识别意图或业务对象。」 | 图片未读；understand → dialogue，未进 disambiguate |
| 2 | 「有点问题」+ 同一张照片 | 「请具体描述一下遇到的问题，例如设备无法开机、运行异常或有异响等。」 | disambiguate → clarify，**reason=product，attempts=1**（问的却是症状） |
| 3 | 「运行异响」 | 「请问您的扫地机器人具体是什么型号？」 | clarify，reason=product，attempts=2（这才是第一次问型号） |
| 4 | 「x00001」 | 「我已整理当前问题记录，您可以复制给人工客服继续处理。」+ 摘要卡 | 目录零命中，attempts≥2 → R7 → summarize |

用户**被问型号只有 1 次，回答了 1 次**，随即终止。摘要里写的「连续 2 次澄清（product）并收到回答后仍无法确认」是事实错误。

## 二、R7 的触发机制

全仓四个触发点，本会话走第一条：

| # | 位置 | 条件 |
| --- | --- | --- |
| 1 | `sessions/clarify.py:198` `_clarify` | 同一 reason（product / symptom / conflict）的 attempts ≥ `MAX_CLARIFICATIONS`(=2)，且本轮是对上一问的回答 |
| 2 | `sessions/clarify.py:182` | 诊断决策 outcome=escalate（症状信息不足且提不出可区分问题） |
| 3 | `sessions/l3.py:559` | 业务查询缺订单号，consult_attempts ≥ 3 |
| 4 | `sessions/l3.py:886` `prepare_retake` | 照片重传 > 2 次仍不可辨认 |

计数规则：`count_attempt`（clarify.py:214）在**真正发出一次追问或产品确认卡片**时 +1；reason 改变即归零。
判定在 `_clarify` 入口：`attempts = clar['attempts'] if clar['reason'] == reason else 0`。

## 三、为什么直接跳人工

```
escalate(R7)
  → receipt.DIRECT_SUMMARY_REASONS = {R3, R4, R5, R7, R8}   (receipt.py:45)
  → needs_collection() == False
  → route_escalate() 跳过 prepare_receipt，直接 "summarize"  (graph.py:2070)
  → summarize 发 escalation_summary 事件 + reassurance_text  (graph.py:2161)
  → 文案「我已整理当前问题记录，您可以复制给人工客服继续处理。」(summary.py:173)
  → 前端 SummaryCard 固定表头「问题摘要已整理，可复制给人工客服」(SummaryCard.tsx:52)
```

R7 被放进「直接摘要」集合的原注释是「品类不明，无产品可核对」——即既然产品都不知道，收凭证也没用。

关键事实：**后面没有人。** `conversation/reply.py:42` 自述「尚未接入真实人工转接服务」。
所以 R7 的实际效果是：对话终止 + 一段可复制的文本。同时 `analytics/derive.py:16` 把 R7 计入 `SYSTEM_FAILURE_RULES`，本次记为系统失败。

## 四、第一性原理：这个会话本来能走下去

自动客服能可靠交付的最小单位，是**一项有依据、适用、风险可控的下一步**。
判断能否推进的标准应当是「现在能不能选出这样一步」，而不是「字段填满了没有」。

按这个标准核对本会话（只读核对，结果见 findings.md）：

- 目录里 `in_scope=True` 的品类只有 `robot_vacuum`，其余五个（吸奶器、移动电源、充电器、耳机、摄像头）全部超范围。
- `get_plans().allowed_for(category='robot_vacuum')` 非空：`rv_suction_hair_wrap`、`rv_suction_filter_clog`、
  `rv_suction_dustbin_full`、`rv_suction_side_brush`、`rv_suction_motor_fault`、`rv_power_supply`。
- 用户第 3 轮给出的「运行异响」正落在 `rv_suction_*` 这组上。
- `clarify.decide`（clarify.py:154-163）只要 `category` 非空且该品类有通用计划，就置 `product_state=category_only` 并 continue 进入诊断。

**即：拿到品类就够了，型号不是闸门。** 系统却为了型号把会话耗死。

为什么没拿到品类？`category` 的唯一来源是 `catalog.category_hint(text)`——纯关键词子串匹配（catalog/service.py:193-199）。
实测 `'有点问题'`、`'运行异响'`、`'x00001'` 均返回 None，`'扫地机器人'` 才返回 robot_vacuum。用户恰好没打出那三个字。

而模型在第 3 轮的追问里已经写了「您的**扫地机器人**具体是什么型号」——**模型已经认定了品类，状态里却是 None**。
模型的理解没有回流到状态，只体现在话术上。这是「多轮对话、分析和理解」失效的具体位置：
理解发生了，但没有任何机制把它变成可推进流程的状态。

## 五、四处具体缺陷

### 1. 产品未确认时永远不读图（最致命）

`graph.py:335-340` `_after_product`：

```python
if state.get("product_state") not in ("confirmed_sku", "category_only"):
    return "reply"
...
return "vision" if _new_fault_images(state) else "retrieve"
```

读图节点排在产品确认**之后**。于是用户主动发了两次设备照片，系统全程没看，最后以「产品型号或品类仍未确认」结案。

更矛盾的是 `clarify.py:284` 的兜底文案本身就是「请补充设备品类，**或拍一张机身型号标签**」——
系统让用户拍照，流程却设计成产品没确认时不读照片。

### 2. 追问预算的计数口径与实际问题内容脱节

attempts 记在 reason=product 上，但问什么由模型自由生成。第 2 轮记的是 product 预算，问的是症状。
产品预算被一个不是产品的问题吃掉一半，用户只剩一次机会。

这与 9/15 上午会话 2702fe9b 那份报告里「症状追问与产品追问共用计数」是同一个病的另一半。
`2026-09-15_diagnostic-first-principles/implementation.md` 修的是「产品兜底不继承症状次数」，
反向的这条——产品预算被症状问题消耗——没有覆盖。

### 3. 零命中型号的处理不符合常识

用户给了明确型号串 `x00001`，目录零命中。合理动作有三个：出产品选择卡、请用户拍机身标签、或按已知品类降级。
`fixed_question`（clarify.py:284）里正好有这条文案：「您提供的型号暂未匹配到产品目录。请补充设备品类，或拍一张机身型号标签。」
但此时 attempts 已满，这句话永远没机会发出。**用户唯一一次提供型号，换来的是终止。**

### 4. 空文本 + 图片没有兜底

第 1 轮把空字符串交给模型解释，模型如实回答「用户输入为空，无法识别意图或业务对象」，
这句内部口径被当作客服话术直接发给用户。`intake/extract.py:96` 只向模型传一个
「（用户同时上传了图片）」的字符串提示，模型看不到图本身。

## 六、最小修复顺序（按「改一处能否救回本会话」排序）

1. **决策前先问「现在能不能动」**：`decide` 在判定 product unknown 之前，先检查现有信息能否选出适用计划。
   本会话有「运行异响」+ 唯一在范围品类 → 直接 category_only 继续排障。
2. **模型理解回流状态**：understand / clarify 已断定的品类必须写进 `state.category`，不能只出现在追问话术里。
   `category_hint` 保留为正向补充，不作为唯一来源。
3. **产品未确认时也读图**：当 `product_state == unknown` 且本轮有 fault 图时，先进 vision 再判 disambiguate。
4. **attempts 按实际问出口的 reason 记账**，或对模型生成的追问做 reason 一致性校验，不一致则回退固定文案。
5. **零命中型号不直接终止**：至少发一次「型号未匹配」文案或出品类选择卡，再计入终止条件。
6. **空文本 + 图片直接走读图**，不交给文本模型解释。
7. **摘要文案与事实对齐**：写实际问过几次、问的是什么，不要固定成「连续 2 次澄清（product）」。

前三条任一条单独生效，本会话都不会到 R7。

## 七、边界

- 本次只读诊断。未改业务代码、未改会话状态、未部署。目录与计划为进程内只读查询。
- 修复 1/2/3 之后本会话会进入 `rv_suction_*` 计划，但这些计划对「异响」的实际覆盖质量未在本轮验收，
  需要另行核对步骤正文是否适用于未知型号的扫地机。
- 「尚未接入真实人工转接」是既有已知边界，不在本次修复范围，但它决定了 R7 是终点而非转交，
  因此 R7 的触发条件应当比现在保守得多。
