# 发现与决策

## 1. 复现事实（会话 10c5eeaf46004f2dbdf951fd0d4d65e4，2026-09-17）

输入：纯图 → 「有点问题」+ 同图 → 「运行异响」→ 「x00001」→ 「扫地机器人」；照片 `data/demo-photos/1_滚刷缠绕_正常曝光.png`。

- 第 1、2 轮 `diagnose.vision` 观察均含「滚刷表面缠绕大量毛发」；`vision_vocab.yaml` 签名 `{滚刷, 缠绕} → rv_suction_hair_wrap`。
- 三次追问品类，`visual_product` 始终为空。
- 末轮 `fault_plan_ids = [rv_suction_motor_fault]`（单步「确认异响后停机等人工」，`next_on` 全 EXHAUSTED）。hair_wrap 未进候选。

## 2. 根因

### 2.1 照片签名进不了候选集

`fault_localization` 由 vision 节点写入（graph.py:428），`reduce.py:64` 初始化为 None，此后没有任何地方清空，
第 5 轮 retrieve 时仍在。retrieve（graph.py:1658-1668）确实把签名命中的 plan 排在 fault card 最前，
但紧接着按 `symptom_codes=state.symptom_codes` 过滤：

```
allowed_ids = allowed_for(category, sku, symptom_codes=[abnormal_noise])
fc_hits = [f for f in fc_hits if f.plan_id in allowed_ids]      # hair_wrap 被筛掉
```

同一过滤还出现在 `_synthesize_step`（graph.py:2015）与 `decide_symptoms` 的 `selected`（decision.py:262）。
三处都以 `symptom_codes` 为门槛，而 `symptom_codes` 只来自 `kind == "symptom"` 的事实
（decision.py:22-27 `_active_facts`）。vision 节点写的事实是 `kind: "observation"`（graph.py:500），不带 `symptom_codes`。
所以照片证据在症状层面是「零」：文字一说「异响」，候选集就只剩 abnormal_noise 的计划。

### 2.2 部件观察不算品类线索

graph.py:419 用 `catalog.category_hint(observation)` 从观察句推品类；`products.yaml:6` 的 robot_vacuum 关键词只有整机词
（扫地机、扫拖机器人、robovac…）。「滚刷」「尘盒」不在其中，`visual_product` 为空。

## 3. 决策

### 3.1 签名 → 症状事实（方案 1）

在 vision 节点，对每条可用 finding（部件与现象可辨、有 evidence）按词表签名找到 plan，
把该 plan 在 `plans.yaml` 声明的 `symptom_codes` 写成一条 `kind: "symptom"` 的事实：
`source_kind: "image_signature"`、`quote: "滚刷缠绕"`、`value: "图片：滚刷缠绕"`、`symptom_codes: [suction_low]`。
相同 value 的 active 事实已存在则不重复写（同一张图重传两次会读两次）。

为什么写成症状事实而不是改过滤逻辑：三处过滤都读 `symptom_codes`，改一处漏两处；而
`symptom_taxonomy.yaml:15-20` 的注释已经把「滚刷+缠绕 → rv_suction_hair_wrap → suction_low」称为
「同一条已审核的知识」并补进了文字路径——图片路径写成同一种事实，两条路径在决策层就等价。

用 `plans.yaml` 的 `symptom_codes`（`PlanLibrary.get(pid).symptom_codes`），不用 `fault_cards.yaml` 里那份：
`allowed_for` 过滤的是前者；后者只用于 fault card 的关键词匹配，且两者不一致（如 filter_clog 在 cards 里写 `[filter_clog]`，
在 plans 里写 `[suction_low, filter_clog]`）。

**不强制安全停机计划排前。** 「异响」不是 `safety_terms.yaml` 里的风险词；R4 / `allowed_operations`
才是 `decide_next` 的安全闸。`rv_suction_motor_fault` 唯一一步是「停用等人工」且全部 `next_on → EXHAUSTED`，
硬把它排前等于让照片证据白读。codes 变成 `[abnormal_noise, suction_low]` 后它仍在候选集里，
hair_wrap 步骤耗尽进 reassess 时它还在。这与我在任务卡片和选项文案里写的「仍须排前」不同，需用户知悉。

### 3.2 部件 → 品类线索（方案 2）

`vision_vocab.yaml` 新增 `category_parts: {robot_vacuum: [滚刷, 边刷, 尘盒, 吸口, 基站]}`——只列品类特有部件；
传感器 / 电池仓 / 充电触点 / 轮组各类设备都有，不作线索。vision 节点把 findings 里这些部件推出的品类并入
`visual_product.category` 的候选集，仍要求唯一才写入。之后沿用现有链路：`clarify.decide` 取 `expected_category`，
固定文案「照片中的设备看起来是扫地机器人，请确认是这个品类吗？」，用户「是」才落 category。
不从部件静默锁品类，遵守 evidence-next-action 的决策。

用 findings（`normalize()` 后按词表归一）而不用 `visible_parts`（模型原话，未归一）。

## 4. 不做

- 不改 vision 提示词、不改模型调用次数。
- 不改 `_active_facts` 的定义、不改三处过滤的代码。
- 不动 `rv_suction_motor_fault` 的步骤内容与覆盖深度（知识问题，另行处理）。
