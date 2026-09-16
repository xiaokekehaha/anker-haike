# R7 误升级根因与第一性原理重构建议

> 状态更新（2026-09-15）：本文保留原始故障分析。当前实现已修复历史状态覆盖等问题，并补充共同计划约束、问诊进展预算及可追溯摘要；后端全量 831 项测试通过，新增改动尚未部署。详见 [实施说明](../planning/2026-09-15_r7-solution-review/implementation.md)。

- 样本会话：`2702fe9bdd4942e9ab84122d42a6848e`（2026-09-15 02:57，lane=domestic）
- 结论：这是一次**误升级**。系统在判别树已经收敛到唯一故障族（`不充电`/`charging_failure`）的情况下，
  因为状态标志被覆盖，仍然判定「无法确认」并以 R7 转人工；全程 `retrieval_calls=[]`，知识库一次都没查。

## 一、逐轮还原

| 轮 | 用户 | 系统 | 关键内部状态 |
|---|---|---|---|
| 1 | `eufy X10 Pro Omni\r\n启动不了` | 追问「设备按电源后能正常启动吗？」 | product_state=confirmed_sku；symptoms=["启动不了"]；symptom_codes=["power_failure"]；interview.status=asking，candidates=8 |
| 2 | `不能` | 追问「放回基站后，设备有正常的充电指示或充电语音吗？」 | 答案已采纳（symptom_answered=true），candidates 收缩为 `[不开机, 不充电]`，但 status 被写成 **superseded** |
| 3 | `不能` | 「我已整理当前问题记录……」→ escalate R7 | candidates 收缩为 **`[不充电]`（唯一解）**，status 仍被写成 **superseded**→随后 `insufficient` |
| 4 | `还有其他的方案吗` | 模型自行给出基站供电/触点清洁/重新归位三步排查 | 证明模型本可以继续排障 |

会话级指标：`clarifications=2`、`steps_executed=0`、`fault_plan_ids=[]`、`knowledge_status=null`、`retrieval_rounds=0`。

证据（checkpoint blob，升级那一刻的 symptom_interview）：

```json
{"candidates": ["不充电"],
 "answers": [{"question": "设备按电源后能正常启动吗？", "answer": "no"},
             {"question": "放回基站后，设备有正常的充电指示或充电语音吗？", "answer": "no"}],
 "status": "superseded", "question": null}
```

`candidates` 只剩一个 —— 信息是够的；`status` 说信息不够。**数据与标志位自相矛盾。**

## 二、缺陷链（五个独立缺陷串成一次误升级）

### D1 词表漏词，且规则被当成否决器
`config/symptom_taxonomy.yaml` 的 `不开机` 族收了 `不开机/开不了机/按了没反应/无法启动/开机没动静`，**没有「启动不了」**；
`clarify.py:41-78` 的 `_SYMPTOM_WORDS` 同样没有。于是 `_has_symptom_text()`（`clarify.py:304-313`）
走到最后的 `len(rest) >= 6` 兜底，「启动不了」只有 4 字 → 判定「用户没有描述故障」。

问题不在漏了一个词（词表永远会漏），而在**这条规则是否决式的**：返回 False 就强制进入澄清，
模型已经抽到的事实不能翻案。封闭词表用来做开放世界的否决，必然高频误杀。

### D2 双轨真相，且没有仲裁
同一句「启动不了」产生了两条互不相认的结论：
- 事实层：`symptoms=["启动不了"]`、`symptom_codes=["power_failure"]`（模型抽取，`canonical_codes` 采信 model_code）
- 判别层：`symptom_interview.candidates`（规则判别树）
- 原文层：`_has_symptom_text(text)` 的正则

三者没有合流点，也没有谁覆盖谁的规则 —— 只有隐式的执行顺序。最终判别树得出 `不充电`，
事实层挂着 `power_failure`，两者矛盾，无人处理。

### D3 决定性 bug：`superseded` 覆盖 `narrowed`
`orchestrator/app/conversation/reduce.py:295-302`：

```python
issue["symptom_interview"], symptom_answered = interview_answer(...)   # 这里刚算出 narrowed
codes = [... 来自 active symptom facts ...]                            # 第 1 轮起恒为 ["power_failure"]
if codes:
    if issue.get("symptom_interview"):
        issue["symptom_interview"] = {**issue["symptom_interview"],
                                      "status": "superseded", "question": None}   # ← 立刻覆盖
```

因为第 1 轮就存下了一条带 code 的 symptom fact，`codes` 此后**每轮都非空**，
于是**每一轮刚采纳的判别答案都会被立刻标成 superseded**。而 `clarify.py:220-224` 只认两种状态：

```python
if interview.get("status") == "narrowed":  ... continue
if interview.get("status") == "asking":    ... _symptom_clarify(...)
```

`superseded` 两条都不匹配 → 穿透到 D1 的 `_has_symptom_text` 否决器 → 再问一次 → 第 3 轮触发 R7。

`superseded` 的原意是「用户直接说清楚了，不用再走判别树」，是**成功**语义；
但它被写在采纳答案之后，实际效果是**丢弃**判别结果。

### D4 R7 的停止条件是代理指标
`clarify.py:254-266` 的判据是 `attempts >= MAX_CLARIFICATIONS(2)`，只数「问了几次」，
不看「问出了多少信息」。本例两次提问各自把候选集从 8→2→1，信息增益是满分的，
却因为次数到 2 被判定为「连续澄清后仍无法确认」。计数器与它想代表的目标完全脱钩。

### D5 转人工摘要文案与事实不符
`orchestrator/app/escalation/summary.py:33` 把 R7 硬编码为「产品品类无法确认」。
本例产品是 `eufy X10 Pro Omni`、`confirmed_sku`、品类 `robot_vacuum` —— 全部已确认。
人工坐席拿到的第一行结论就是错的，且 `hypotheses=[]`、`steps=[]`，
两轮问答得到的 `不充电` 结论**完全没有进入摘要**。

## 三、第一性原理：应该重做什么

第一性目的：**用最少的用户轮次，把一次故障收敛到一个可执行动作（步骤 / 工单 / 人工）。**
由此推导，系统里唯一有价值的状态是「当前假设分布」和「每轮的信息增量」。对照现状：

### R1 真相必须单源 —— 合并成一个「假设集」
现在有三套并行真相（facts.symptom_codes / interview.candidates / 原文正则），靠执行顺序互相覆盖。
应当只保留一个 issue 级的 `hypotheses: {fault_family: 证据来源列表}`：
模型抽取、规则词表、判别问答都只是**往同一个集合里加减证据**，各自带 source 与 confidence，
不再有「谁覆盖谁」。D2、D3 从结构上消失。

### R2 停止条件必须基于信息增益，而不是提问次数
把 R7 重定义为：**连续 N 轮候选集不收缩（或熵不下降）→ 升级**。
本例 8→2→1 永远不会触发；真正该触发的是用户连答「不知道」导致候选集纹丝不动的场景。
`attempts` 可以保留为硬上限（防死循环），但不能是主判据。

### R3 状态是派生量，不是存储量
`status` 应该由 `len(candidates)` 和 `answers` **算出来**，而不是存一个字段让各处覆盖。
只要 `status` 是可写字段，D3 这类覆盖 bug 就会反复出现。等价地：
`decide()` 不该读 `status`，应该直接读 `candidates`——`len(candidates)==1` 就是可以继续。

### R4 规则表只能加速，不能否决（开放世界假设）
`_has_symptom_text` / `_SYMPTOM_WORDS` / taxonomy expressions 都是封闭词表。
它们可以**肯定**（命中 → 直接确定），但不能**否定**（未命中 ≠ 用户没描述故障）。
未命中时的正确动作是降级到模型判断或直接进判别树，而不是强制澄清。
`len(rest) >= 6` 这种字数启发式应当整体删除。

### R5 提问必须以「已知」为条件
`taxonomy.py:38-49` 的 `select_discriminator(candidates)` 只看候选集，不看用户已经说过什么。
结果第一个问题「设备按电源后能正常启动吗？」几乎是复述用户原话「启动不了」——
用户会明显感到没被听懂。判别树必须**先用已有证据（原文 + 模型抽取）做一次先验裁剪**，
再从剩余候选里选问题；被原文直接回答过的判别器要跳过。

### R6 升级不是终态，而是「并行输出」
本例在 `candidates=['不充电']` 时零检索就转人工，而第 4 轮模型自己给出了正确的三步排查。
升级应当是「同时给用户当前最优步骤 + 准备好人工摘要」，而不是用一句
「我已整理当前问题记录」中断服务。至少：**升级前必须至少完成一次检索**，
让摘要里带着 hypotheses 和已试步骤。

### R7 转人工摘要必须是可审计的因果链
`REASON_TEXT` 的静态映射要换成结构化归因：规则 ID + 触发时的真实状态快照
（product_state、candidates、answers、已试步骤、检索结果），文案由此渲染。
「R7 → 产品品类无法确认」这种与事实相反的硬编码结论，对人工侧是负价值。

## 四、修复优先级

| 优先级 | 动作 | 落点 |
|---|---|---|
| P0 | 采纳判别答案后不得覆盖 `narrowed`；或 `decide()` 改看 `len(candidates)==1` | `reduce.py:295-302`、`clarify.py:220-224` |
| P0 | R7 文案改为按真实触发原因渲染（本例应为「故障现象无法确认」且必须带上已收敛结论） | `escalation/summary.py:24-35` |
| P1 | R7 判据改为「候选集连续 N 轮不收缩」，`attempts` 降级为硬上限 | `clarify.py:254-266` |
| P1 | 判别问题选择先做先验裁剪，跳过用户原文已回答的判别器 | `taxonomy.py:38-49`、`_symptom_clarify` |
| P1 | 升级前强制至少一次检索，摘要带 hypotheses / steps | `graph.py` escalate 路径 |
| P2 | `_has_symptom_text` 由否决器改为加速器，删除 `len(rest)>=6` 启发式 | `clarify.py:304-313` |
| P2 | 三套症状真相合并为单一 `hypotheses` 结构 | `reduce.py`、`taxonomy.py`、`clarify.py` |
| P2 | 补词（`启动不了` 等）—— 只是止血，不解决 R4 的结构问题 | `config/symptom_taxonomy.yaml` |
