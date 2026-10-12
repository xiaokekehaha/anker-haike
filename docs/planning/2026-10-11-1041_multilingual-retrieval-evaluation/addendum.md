# 评审补充（2026-10-11，另一会话写入，plan.md 保持原样）

来源：Fable 5.1 只读评审 + 21:03 续测记录（`docs/planning/2026-10-10-2103_official-63-continuation/`）。供实施时参考，不改 plan.md 的结论与门槛。

## 1. 已过时的描述

- findings.md 记「工作区有其他会话改动 synthesize.py / qa_index.py / graph.py，本次不改」：这些已分别提交为 9475154（愿望句、推荐句、笼统现象追问、配件对象）
  与随后一个提交（笼统现象追问改为引客户原话、与症状追问共用预算）。graph.py 现在只剩本方案实施中的 `search_query_en` 改动未提交。
- T43 终点已从 R5 变成「先请客户把原话说具体」：评估 T43 时 Hit@k 不再是唯一指标，还要看追问后是否召回。

## 2. 非英语工单的实际表现（21:03 轮）

| 工单 | 语言 | 路径 | 结果 |
| --- | --- | --- | --- |
| T6 | nl | 物流 | 正确，与检索无关 |
| T13 / T18 / T22 / T28 | nl / nl / nl / de | 错误码精确命中 | 不经语义检索 |
| T20 | nl | 语义 | 金标 rank 1 |
| T21 | fr | 语义 | 「capteur laser bloquer」召回 rv-0235 / rv-0231（rank 1–2），实际是正确条目，cases.yaml 未标金标 |
| T36 | nl | 语义 | 召回 rv-0341（rank 4），首轮问滚刷隔离 |
| T37 | nl | 语义 | 金标 rank 3 |
| T43 | es | 语义 | 唯一失败：召回全是 7002 / 7000 离地、被困 |

10-08 检索报告（`reports/retrieval/20261008T131009Z_qa-relabel.md`）13 个现象单 Hit@5 77%，3 个未命中全是英语（T40 no_scope、T57 / T59 摄像头离线）。

## 3. 应加的英文孪生对照组

**T39 是 T43 的英文版**（「The robot is offline.」，同为 T2351）。T39 查询「robot offline」的 15 条命中与 T43 几乎同一批离地条目，只多 rv-0098（固件升级后离线，rank 6，标题字面含 offline）；
rv-0271 / rv-0014（连不上 Wi-Fi）中英文都不出现。含义：

- 人工忠实英文（H 组）对 T43 的预期上限约等于 T39 的结果，不是 Wi-Fi 条目；
- 「offline / disconnected」的语义邻域被标题里的「robot」词面命中淹没，问题主要不在语言。

建议 §2 的三组比较加入孪生对照：T43 ↔ T39，T57 / T59 ↔ T56。

## 4. 先补两项零风险观测，再做对照

- **检索权重**：WeKnora hybrid-search 是 BM25 + 向量的加权 RRF，源码默认向量 0.7 / 关键词 0.3、k=60（`docs/planning/2026-09-12_weknora-usage-explanation/findings.md:58-62`），
  当前运行空间的实际配置未核。若向量侧在起作用、embedding（text-embedding-v4）又是多语言，T43 的修复方向可能是权重 / 阈值，而不是翻译。
- **命中来源**：WeKnora 命中自带 `match_type`（`app/knowledge/adapter.py:6` 提到），但 `Hit` 构造（adapter.py:300-315）丢掉了，trace 看不出哪一路命中。建议 `Hit` 保留并写进 retrieval_trace，
  再加一个「向量单路」对照组（V 组）。

## 5. 方案未覆盖的语言问题：读图中文描述进英文库查询

图片补查把 diagnose.vision 的**中文**观察拼进查询（T20 / T38 / T46 / T53 / T55 第二轮 query 带「黑色基站放在木地板上…」）。
本轮没造成失败（首轮已命中），但这一路补查对英文库基本无效。D 组（补查触发）应把它单列；修复方向可以是 vision 观察输出英文或补查时不拼中文描述。

## 6. 金标来源

§3 拟新建 `data/eval/retrieval_multilingual.yaml`，而 `app/knowledge/eval.py` 只读 cases.yaml 的 qa_gold，两份金标源会漂移。建议：

- T21（rv-0231 / rv-0235）、T36（rv-0341）的相关 Q&A 直接补进 cases.yaml；T43 标 needs_clarification，不给金标；
- 新文件只放 human_query_en、relevance_status 这类附加字段。

## 7. 对「intake 顺带输出英文症状摘要」实施的评审要点

（实施完成后由提出评审的会话复核，这里先列检查项）

- 摘要只进检索：不写进 facts / symptoms / 交接摘要 / synthesize 的有效症状；`search_query_en` 绑定本轮事实版本，事实更正或切换问题后不能沿用旧摘要。
- 英语工单不应改变行为（摘要与原文同义时合并后命中集合不变）；精确码路径不受影响。
- 合并方式要能在 trace 里区分原文与英文两路各自的命中，便于按上面 §3 / §4 归因。
- intake 输出字段增加后，抽取准确率与输出预算需在真实模型上回归（INTERPRET_PROMPT_VERSION 递增）。

## 8. A2 运行配置复核（2026-10-11，Codex）

本节为只读核查，更新 §4 的“实际配置未核”状态；不改权重、日志级别或应用代码，不重启服务，不发起新的模型/检索调用。

### 已确认

- 当前本机容器 `haike-weknora-app-1` 镜像为 `wechatopenai/weknora-app:v0.8.0`，镜像 ID `sha256:14953fcb990c59b2546f00e94673d2a4c88689e3319bfcf2b06f82feaccec9b4`，revision 标签为 `1edcd54b43606d9079bb36650efe3f68707a79ea`。
- 只读查询 `SELECT id, retrieval_config IS NULL AS uses_defaults FROM tenants ORDER BY id;`：租户 10000、10001 均为 true。具体检索日志 effectiveTenantID 为 10001。
- 对应源码 `GetEffectiveRRFWeights()` 在 nil 配置返回向量 0.7、关键词 0.3；`GetEffectiveRRFK()` 返回 60；HybridSearch 将 tenantInfo.RetrievalConfig 传给融合函数。因此当前本机该路径使用默认值。此结论不外推到远程生产环境。
- 项目适配器只传 query_text、match_count 和 knowledge_ids，未设置融合权重，也未禁用任一路。
- Hit 定义与 adapter.py:309 的构造都未保留 match_type；上游原始响应字段在此被丢弃。

### 可关联的当前日志

| 时间（容器日志） | 请求 ID | 查询 | 向量候选 | 关键词候选 | 融合后候选 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-11 11:24:33 | 61a5242e-139a-4dea-b0ff-c6b9ca586a9b | The robot is offline. a | 75 | 75 | 82 |
| 2026-10-11 11:24:33 | 2f54a6ac-22f9-451a-98a3-390cca99da62 | El robot está desconectado | 75 | 75 | 82 |

英语查询末尾的 `a` 是日志原样，不能将该记录伪装为严格的英文孪生对照。两条记录证实向量、关键词均工作，但数量不证明候选质量或排序贡献。本轮未关联到用户所指中文查询的确定请求，不宣称已复现中西对照。

### 权重的准确含义

RRF（倒数名次融合）对同一 chunk 按两榜排名加分：`0.7/(60+vector_rank) + 0.3/(60+keyword_rank)`；未进入某一路榜单则该项为 0。它不是向量相似度乘 0.7，也不保证最终结果 70% 来自向量。仅一路有结果时，源码绕过 RRF，保留原始分数。

### match_type 不能单独做归因

上游 fuseWithRRF 按 chunk 合并时优先保留向量结果对象，再把 score 改成融合分；buildChunkIndex 和 buildSearchResult 沿用该对象的 MatchType。同一 chunk 两路均命中时，标签可能仍显示向量，不会完整表达两路贡献。附近块、关联块还会使用扩展类型。

因此补回原始 match_type 有观测价值，但不应把它转成 vector-only / keyword-only / both 的确定分类。真正的贡献需要 vector_rank、keyword_rank、各自贡献分、融合名次和最终保留情况。源码已有逐条 RRF rank 的 Debug 日志；本轮最近 3 小时日志未找到该项。

### 对假设的裁决与下一步

- 同意先核对检索配置与来源；现在权重已确认。
- “关键词主导”尚未证实；两路都返回候选，标题含 robot 也可能是向量同样未识别离线语义或两路共同偏向泛词。也不能反向根据 0.7 权重声称向量结果必然正确。
- 下一项最小对照是同一查询、同一知识库和产品范围下的 vector-only / keyword-only / hybrid；保持 match_count、阈值、上下文扩展选项一致，记录正确条目的候选名次与最终进入上下文情况。
- 使用请求级 disable_keywords_match / disable_vector_match 做单路对照；不能把权重设 0 当作禁用，GetEffectiveRRFWeights 会对非正权重回退默认值。
- 若向量单路已正确、混合后消失，再评估权重；若向量单路也失败，优先检查表示、查询与索引；若候选有而上下文没有，检查截断与合并。不要先改全局权重或把翻译当作已成立的修复。

源码依据：

- [默认参数](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/retrieval_config.go)
- [融合与元数据保留](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_fusion.go)
- [租户配置传入检索](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search.go)
- [结果构造](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/application/service/knowledgebase_search_results.go)
