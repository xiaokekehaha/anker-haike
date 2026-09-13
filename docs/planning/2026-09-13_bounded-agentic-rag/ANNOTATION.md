# 评测集标注指南

要标注的文件只有一个：**`data/eval/retrieval/cases.yaml`**（56 条）。
标注完成后，[switches.md](switches.md) 里那三个「建议开」的开关才有正式判据。

## 为什么要标注

样例是我依据 `data/knowledge/` 的语料起草的，金标属于「看着像」，没人核过。task_plan 的硬约束写着：未标注的样例只能作回归对比，不能作为开启开关的依据。起草时已经暴露出至少两条金标是错的（见下面示范 B），所以这一步不能省。

## 怎么做

### 1. 生成工作单（把「金标 vs 实际召回」并排摆好）

```bash
make kb-eval ARM=A && make eval-worksheet
```

产出 `reports/retrieval/worksheet.md`，每条样例一节：用户原话、实际发出的 query、现有金标、模型选了哪个计划，以及实际召回的 top-5 片段。对着它改 yaml，不用自己去翻语料。

### 2. 逐条判断三件事

| 判断 | 看什么 | 改哪个字段 |
| --- | --- | --- |
| 召回里哪些**确实**是回答这个问题的依据 | 工作单的 top-5 片段 | `expected_doc_ids`（手册 / FAQ）、`expected_ticket_cause`（工单按根因） |
| 期望模型选哪个排障计划 | `config/plans.yaml` 的 5 个计划 | `expected_plan`（没有合适的写 null） |
| 这一轮该走证据、标准流程还是升级 | 有无适用计划、是否触发安全规则 | `expected_outcome` |

判断口径：

- **相关就算金标**，不要只保留「最相关的那一条」。指标算的是 top-5 里有多少条是依据，漏列会把 precision 压低，反而让改进看起来像退步。
- **工单用 `expected_ticket_cause`**，不要逐条列 id。同因工单往往有好几条（T0178 / T0168…），命中片段里含「原因：<该值>」即算金标。
- **未解决工单不是依据**。它只能作反证，不该进 `expected_doc_ids`。
- **FAQ 要算**。FAQ 之前根本没被检索到（阶段 3 才接上本地索引），所以起草时的金标普遍漏了它。
- **无知识样例保持空金标**。`none-*` 那几条期望的就是「不该有依据」，空的 `expected_doc_ids` 会让评测按泄漏统计。
- **安全类样例的 outcome 是 escalate**，但那由安全规则在检索之前决定，评测脚本不比较这几条的 outcome，照实写即可。

### 3. 标记完成

每条改完补上：

```yaml
annotated: true, annotator: <你的名字>,
note: "<日期> 标注：<判断依据，尤其是改了金标的原因>"
```

文件头的 `annotated_count` 同步改成实际条数。

### 4. 重跑对照

```bash
make kb-eval ARM=A
cd orchestrator && uv run --env-file ../.env haike-kb eval --arm C_nograde \
  --config ../data/eval/retrieval/configs/C_nograde.yaml --with-synthesize
```

看 C_nograde 的 `plan_match` / `outcome_match` 是否仍优于 A。是，就按 switches.md 第 3 步开三个开关。

## 两条示范

文件里的 `bin-01` 与 `chg-03` 已经标好，覆盖两种最常见的情况。

### 示范 A：`bin-01` —— 金标方向对，但漏列了同样相关的依据

用户说「一直语音说请检查尘盒，我明明装上去了」。实际召回 top-5：

| # | 来源 | 内容 | 是依据吗 |
| --- | --- | --- | --- |
| 1 | manual_rv_v1 | 1.3 清理尘盒（c18），装到位听到咔哒声 | 是 |
| 2 | faq_rv | 问：提示请检查尘盒是什么意思 | 是 |
| 3 | T0063 | 同 SKU 同现象，原因：尘盒未装到位 | 是 |
| 4 | manual_rv_v1 | 第 3 章指示灯表，「请检查尘盒」行 | 是 |
| 5 | faq_rv | 问：语音提示请检查滚刷 | 否，但排第 5，可接受 |

原金标只写了 `[manual_rv_v1, troubleshooting_rv]`，漏了 FAQ 和工单。改完：

```yaml
expected_doc_ids: [manual_rv_v1, troubleshooting_rv, faq_rv]
expected_ticket_cause: 尘盒未装到位
expected_chunk_hint: "c18 / 第3章表 / C / faq q5"
annotated: true, annotator: kelly.zhou
```

### 示范 B：`chg-03` —— 起草金标判错了，要改

用户说「找不到回家的路，每次都停在半路」。原金标写的是排障手册 `troubleshooting_rv` 的 E 节，但 E 节讲的是「充不上电」，根本没提找不到基站。实际召回里真正的依据是 FAQ q14（机器找不到基站）和同 SKU 同因工单（基站位置遮挡）。改完：

```yaml
expected_doc_ids: [faq_rv]
expected_ticket_cause: 基站位置遮挡
expected_chunk_hint: "faq q14"
expected_plan: null            # plans.yaml 确实没有对应计划，保持 null
expected_outcome: standard_flow
irrelevant_hint: 排障手册 E 节是充电问题，不算本题依据；manual_rv_v2 安全须知因「基站」二字被召回，属错配
annotated: true, annotator: kelly.zhou
```

这条同时说明 `irrelevant_hint` 怎么用：把「看着像但其实不是」的召回记下来，后续统计错配时有依据。

## 已知需要重点看的几条

起草时就发现有问题、建议优先处理：

| 样例 | 问题 |
| --- | --- |
| `ctr-03` | 金标写了 T0030，实际命中 T0130，同为「雷达窗口脏污」且都是未解决工单 → 改用 `expected_ticket_cause` 并确认未解决工单不该当依据 |
| `cat-05`、`none-01`、`none-03`、`none-04` | 标了 `faq_only`，起草时 FAQ 不在检索范围所以按「无知识」写；现在 FAQ 已接入，要重判是有依据还是真无知识 |
| 9 条 `无计划` 标签 | 充电 / 拖布 / 水箱 / 路线 / 指示灯类有语料但 `plans.yaml` 没有对应计划，确认 `expected_outcome: standard_flow` 是想要的行为 |
| `a2-01` | 起草时工单 id 随手写了 T0001，应换成 EUFY-S1-PRO 的实际工单或改用根因匹配 |
