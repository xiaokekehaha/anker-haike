# 有界 Agentic RAG（LangGraph）落地

## 目标
在 retrieve 节点内实现有界的检索环：确定性多查询 + RRF、一次相关性评分、父块扩展、两轮合并；补齐四项 P0 缺口；建立检索评测集与跑分脚本。全部开关默认关闭，逐项凭数据开启。设计见 [design.md](design.md)。

## 决策（2026-09-13 用户确认）
- 确定性路线：补查方式由代码按固定优先级选，模型不选动作。
- 评测集首批由 Claude 起草，用户续改标注。
- `retrieve.grade` 允许在只有 DeepSeek + 智谱 key 的环境上线，需 bake-off 达标。
- 以 planning-with-files 方式推进（本目录）。

## 阶段
| # | 阶段 | 交付物 | 出口 | 状态 |
| --- | --- | --- | --- | --- |
| 0 | 评估与设计 | docs/claude/spec_agentic_rag_evaluation.md、design.md、评测集草稿 | 用户确认路线 | **complete** |
| 1 | P0 修复 | 两库并发、第二轮硬超时、两轮合并、counter_evidence → case_outcome 进 synthesize；单测 | 现有测试通过，findings 记录 | **complete**（2026-09-13） |
| 2 | 真实链路与基线 | 真实 embedding 重新导入并更新 manifest；`haike-kb eval` 脚本；跑 A 组基线 | `reports/retrieval/20260913T033959Z_A.md` | **complete**（2026-09-13；rerank 见 findings） |
| 3 | S0 + S1 | `diagnose/expand.py`、`knowledge/search.py`（变体并发 + RRF + 跨库交错）、本地 FAQ 索引、适配器侧 rerank；跑 B / B_rerank | 报告 `reports/retrieval/20260913T0353*`；三个开关均保持关闭，待标注后决定（见 findings） | **complete**（2026-09-13） |
| 4 | S4 父块扩展 | `list_chunks`（`GET /chunks/{knowledge_id}`）、手册子块缓存、同父子块拼接还原父块、synthesize 用 full_text、评测加 chunk_hit@5 与 P 组 | 单测 7 个；报告 `reports/retrieval/20260913T0406*` | **complete**（2026-09-13；默认关闭，见 findings） |
| 5 | S2 + S3 grade | `diagnose/grade.py`、S3 决策改造（graded 全不相关视同无命中）、`retrieve.grade` bake-off（qwen-flash 主 / deepseek 备）、`haike-kb eval --with-synthesize` 模型侧对照 A / C_nograde / C | 报告 `reports/retrieval/*_synth.md`、`reports/bakeoff/retrieve_grade/` | **complete**（2026-09-13；结论见 findings） |
| 6 | 改写开启评估 | 用 C 组数据评估 `query_rewrite.enabled`；修 validate_rewrite 词表 | 报告 | pending |
| 7 | 收尾 | 00 / 03 / 08 / 09 / model-selection 回填；RELEASE.md；findings | 文档一致 | pending |

## 硬约束（不随阶段变化）
- 轮数 ≤ 2；首轮请求 ≤ `max_requests_per_round`；第二轮请求 ≤ 2 且整轮 ≤ 3 s。
- 子流程模型调用 ≤ 4（grade ≤ 2、rewrite ≤ 1、synthesize 1）。
- 不新增图节点，不改 SSE 事件与卡片。
- 所有开关关闭时行为与现状一致（阶段 1 修复除外）。
- 未标注的评测样例不能作为开启开关的依据。

## 依赖与阻塞
- 阶段 2 的 DASHSCOPE_API_KEY 已配置（2026-09-13），embedding / rerank 接口均实测可用。
- 阶段 3 起需要评测集至少 50 条 `annotated: true`。
- 阶段 4 需要核对 WeKnora v0.8.0 分块列表 REST 路径。

## 待用户决策（阶段 3 产出）
- `faq.enabled`：B 组 FAQ 命中逐条看几乎全部相关（findings 有清单），但金标未含 faq_rv，precision 指标反而下降；按硬约束不在未标注前开启。建议标注时把相关 FAQ 条目加入 expected_doc_ids 后开启。
- `multi_query.enabled`：文档级 hit@5 与 A 组持平（96%），成本 +50 ms p50；收益只可能在分块级体现，等阶段 4 父块扩展与分块级金标后再评。
- `rerank.enabled`：文档级无增益，p50 +470 ms；bin-03 一例把指示灯表格块顶到 c18 前面。默认关闭，不建议开。
- `parent_expand.enabled`：零模型调用、延迟无差异（p50 230 vs 239 ms）、chunk_hit@5 持平 98%，但「第一条证据含金标段落全文」从 36/49 提到 48/49。建议开；正式判据仍等阶段 5 的 expected_plan 一致率。风险只有上下文变长：每 run 最多 3 段 × 800 字。

- `grade.enabled`：**不建议开**。模型侧对照 plan_match 41/43（C_nograde）→ 39/43（C），两条回归都是金标段落被误剔；延迟 +1.6 s；56 条里 7 条调用失败（优雅降级）。单独探针证明它在命中含无关块时判断正确，但本期语料噪声少，收益抵不过误剔。语料扩大后重评。
- `multi_query + faq + parent_expand`（C_nograde）：模型侧 plan_match 41/43、outcome_match 50/51，均**优于** A 组的 40/43、49/51，延迟 p50 反而略低（3291 vs 3645 ms）。这是三个开关第一次拿到正向判据，建议标注后一并开启。

## Next Step
阶段 6：用 `--with-synthesize` 对照评估 `query_rewrite.enabled` 并修 validate_rewrite 词表过严；顺带把阶段 5 发现的 Qwen 思考模式修复纳入回归（重启 orchestrator 容器验证 domestic 链不再降级）。
