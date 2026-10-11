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
