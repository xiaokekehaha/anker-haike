# intake 英文现象描述参与检索（search_query_en）

时间：2026-10-11 02:50–04:40（北京时间）。评审要点：`docs/planning/2026-10-11-1041_multilingual-retrieval-evaluation/addendum.md` §7。

## 改动

- intake 输出新增 `search_query_en`：有故障现象时用英文转述现象，只用于检索。
  - 只写在问题上（ISSUE_FIELDS），不进 facts / symptoms / 标题 / 交接摘要 / synthesize 的有效症状。
  - 本轮有现象才更新；没有现象的轮次沿用上一轮；切到另一台设备的新问题不带过去。
  - 原文没有的型号 / 错误码不收（会把检索带偏）。
- 检索：`search_round` 原文与英文各查一次，按名次加权 RRF 合并（原文 1、英文 0.5，k=60）。图内与 `haike-kb eval` 同一函数。
  trace 里两路各一条 `knowledge_search`（含 query 与 hit_ids），合并后的 Hit 保留 `source_queries`，能分别归因。
- `haike-kb eval --english <json>`：给定工单 id → 英文描述时双路检索，报告逐单记 `query_en`。
- cases.yaml 补金标：T21（激光传感器条目）、T36（吸尘噪音条目）、T39 / T43（Wi-Fi / 离线条目）。
- intake schema 固定开销上限 2650 → 2740（实测 2689）。

## 检索评测（63 单首封，intake 真实模型生成英文描述）

| 指标（16 个无错误码现象单） | 单路原文 | 双路 w=0.5 |
| --- | --- | --- |
| recall@5 | 69% | 81% |
| 英语单 recall@5 | 64% | 91% |
| recall@12（进入 synthesize 的范围） | 88% | 88% |
| 精确码单也召回@5 | 100% | 94% |

- 提升：T36 3→1、T54 3→1、T26 3→2、T57 / T59（摄像头离线）前 5 外→5。
- 下降：T18 1→7（荷兰语推送「De mop met rol is verstopt」被概括成 mop obstructed；T18 线上走精确码，不受影响）、T37 3→5。
- T43 / T39 两边都没召回 Wi-Fi 条目：英文是「robot is disconnected」「robot shows offline in the app」。手工查「robot offline cannot connect to Wi-Fi」能召回 rv-0271：瓶颈是客户信息太少，不是语言，需保留 b121c5f 的追问。
- 等权（w=1.0）recall@5 同为 81%，但 T27 2→5；k=10 时原文主导过强、收益消失。选 w=0.5、k=60。

报告：`reports/retrieval/20261011T032113Z_single-relabeled.md`（单路）、`20261011T041954Z_dual-en-w05.md`（双路，最终权重；逐单 query_en 即所用英文描述）。

## intake 抽取回归（真实模型，评审 §7）

| 金标 | 加字段后 | 不加字段对照 | 10-09 / 09-14 基线 |
| --- | --- | --- | --- |
| intent（40） | 38 / 40 | — | 38 / 40 |
| emotion（40） | 35 / 40 | 35 / 40（同 5 条：calm 判 null 或 dissatisfied） | 38 / 40（09-14，之后 9eac3f6 加了「calm 也要原话支撑」规则） |
| routing（20） | 20 / 20 | — | — |

emotion 的下降与本字段无关（去掉字段的对照组同样 35/40、同 5 条），来自此前的情绪规则改动，另记。

## 63 单主层真实回放（镜像重建后，串行）

与 21:03 轮逐单比较首张卡片计划与停止原因：55 单一致，8 单不同。

| 案例 | 变化 | 原因 |
| --- | --- | --- |
| T32 | 无卡 → rv-0061 胶带卡 | bdadf1e 的拆卡（预期） |
| T43 | 转人工 → 追问 | 9475154 / b121c5f 的笼统现象追问（预期） |
| T60 | done → 追问现象 | 9475154 的愿望句过滤（预期） |
| T44 | 采证失败 → 等凭证 | 上一轮 journey 404，非业务变化 |
| T51 | bp-0018 → bp-0111 | 都是乳泵供电 / 电池条目；bp-0111 更贴近「电池撑不住」，走完过保关单，路径合理 |
| T56 | 发 bp-0151 → 先追问电量 | 候选判待确认后追问，合理 |
| T3 | 补寄方案 → 只答「Country of purchase: no confirmed record yet」 | intake 偶发把 answer_request 字段列成 country。单独重复 5 次（有 / 无新字段各 5 次）：有字段 0/5、无字段 1/5 出现 country，与本字段无关；属 intake 的 answer_request 抖动，另记 |
| T61 | 追问时机 → 转人工 | 同一原文用新镜像再跑 3 次，3 次都是追问时机（与旧轮一致）；回放那次 synthesize 两批都空，模型偶发 |

单测：检索双路 4 条、reduce 3 条、评测 1 条、整链路 1 条；ci-local 全绿（后端 1280、契约 91、前端 230）。
