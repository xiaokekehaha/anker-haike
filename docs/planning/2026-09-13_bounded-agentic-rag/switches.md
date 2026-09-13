# 检索开关：现状、证据与开启建议

一页速查。全部开关在 `config/retrieval.yaml`，默认**全关**；关闭时链路行为等于阶段 1 修复后的基线。
证据来自 `reports/retrieval/`（检索层 + 模型侧对照）与 `reports/bakeoff/`。评测集 `data/eval/retrieval/cases.yaml` 目前 `annotated: 0/56`，**下面的数字只能作回归对比，不能当作开启依据**（task_plan 硬约束）。

## 一览

| 开关 | 作用 | 额外成本 | 证据 | 建议 |
| --- | --- | --- | --- | --- |
| `multi_query.enabled` | 已审核同义表生成 ≤ 2 个查询变体，变体 × 两库并发，RRF 合并 | 0 次模型调用；p50 +50 ms | 见下 C_nograde | **建议开**（随下面两项一起） |
| `faq.enabled` | 本地 FAQ 索引作为第三个检索源 | 0 次模型调用；≈ 0 ms | FAQ 此前完全没被检索到 | **建议开** |
| `parent_expand.enabled` | 手册命中扩成父块正文给 synthesize | 0 次模型调用；p50 −9 ms（噪声内） | 首条证据含金标段落 36/49 → 48/49 | **建议开** |
| `rerank.enabled` | 适配器侧调百炼 gte-rerank-v2 重排 | 1 次 HTTP；p50 +470 ms | 文档级无增益，有一例把表格块顶到正文前 | **不建议开** |
| `grade.enabled` | 一次 `retrieve.grade` 评分，剔除无关命中 | 1 次模型调用；p50 +1.6 s | plan 命中 41/43 → 39/43 | **不建议开**（本期语料） |
| `query_rewrite.enabled` | 无命中时一次受控改写 + 补检索 | 触发时 1 次模型调用 | 本语料 0/56 触发 | **保持关**（触发不了） |
| `query_rewrite.strict_terms` | 回到早期严格校验（整句须由原文切出） | — | 实测拒掉 6/8 合理改写 | 保持 false |
| `grade.second_round` | 第二轮新增命中再评一次 | 再 1 次模型调用 | 未单独评测 | 保持 false |

## 模型侧对照（56 条，真实模型跑 grade + synthesize）

| 组 | 开关 | plan 命中 | outcome 命中 | synthesize p50 |
| --- | --- | --- | --- | --- |
| A | 全关 | 40/43 | 49/51 | 3645 ms |
| **C_nograde** | multi_query + faq + parent_expand | **41/43** | **50/51** | 3291 ms |
| C | 再加 grade | 39/43 | 50/51 | 3206 ms（另加 grade 1578 ms）|

复现：

```bash
make kb-eval ARM=A
cd orchestrator && uv run --env-file ../.env haike-kb eval --arm C_nograde --config ../data/eval/retrieval/configs/C_nograde.yaml --with-synthesize
```

## 为什么检索层指标看不出差别

手册库一共 13 个子块（3 份文档），top-5 就覆盖单份手册的大半，`hit@5` 与 `chunk_hit@5` 在所有组都是 96% / 98%，已经饱和。三个确定性开关的收益只在 synthesize 的输入质量上体现，所以判据必须用 `--with-synthesize`。

## 开启前建议的顺序

1. 标注评测集（把相关 FAQ 条目补进 `expected_doc_ids`，工单类金标放宽为按 root_cause 匹配，修正 `chg-03` / `ctr-03` 两条金标）。
2. 重跑 A 与 C_nograde 两组，确认 plan / outcome 命中不降。
3. 一次性打开 `multi_query` + `faq` + `parent_expand`，重启 orchestrator，发一条真实会话验活（**换 config 必须验活，见 runbook release.md §3**）。
4. `rerank` / `grade` / `query_rewrite` 维持关闭，等语料扩大或召回噪声上升后用同一套对照重评。

## 回滚

改回 `enabled: false` 并重启 orchestrator 即可，无数据迁移、无契约变更。三个确定性开关不产生任何新的持久化字段；`grade` 只多写 `evidence_quality` 与 trace，关掉即为 `None`。
