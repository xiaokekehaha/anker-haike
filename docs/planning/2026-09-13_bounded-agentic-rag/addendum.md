# 勘误与复核

## 2026-09-18：design.md §3.2 流程图与落地实现不一致

`design.md` 开发开始后保持原样，所以图里的三处已经和 commit `63e2750`
（`feat(diagnose): 候选池与最终证据分离，充分性驱动一次补查`）落地的实现对不上。
实现记录见 `docs/planning/2026-09-18_chain-b-retrieval/implementation.md`。

| design.md 图里的画法 | 实际实现 | 为什么改 |
| --- | --- | --- |
| `G -->\|sufficient\| E` / `G -->\|insufficient 或 none\| D`，grade 在链路上做硬过滤 | grade 只打质量标记 + 给 coverage，不删候选 | 阶段 5 实测硬过滤误剔金标段落，plan_match 41→39（见 findings.md） |
| `D -->\|开关开 且 全部真实 no_match\| R2b` | 触发条件换成充分性：`has_hits 且 coverage==sufficient` 才不补查 | 阶段 6 实测「两库同时 no_match」0/56，最新评测 `no_match 0` —— 旧条件在本语料下是死代码 |
| 图中只有一个 `top_k` | `candidate_k=15` 与 `final_k=12` 分离，中间加 `select_hits / pack_hits` 证据选择层 | 旧实现请求 15 条却先裁到 5 条再重排，重排结构上捞不回第 6–15 条；「rerank 文档级无增益」的结论是在这个前提下得的，不能外推 |

另：`S0 确定性查询扩展` 增加 `multi_query.categories` 品类门槛。同义词表是扫地机专用的，
2026-09-17 语料扩到 7 个品类后，不加门槛会把「吸力下降」那套词套到耳机 / 充电宝查询上。
同义表里的 `刷子 → 滚刷` 已删除：「刷子」在滚刷与边刷之间有歧义，留着等于允许改写替用户推断部件。

### 当前实际流程

```text
build_query（纯函数，不调模型）
  product_state=unknown → knowledge_status=no_query，一个请求都不发
        │
        ▼
KnowledgeScope（sku / category 白名单）
        │
        ▼
S0 同义扩展 expand_queries            [multi_query=false，且限 categories]
        │
        ▼
首轮：变体 × {kb_manual, kb_tickets} 并发 hybrid_search
        │   match_count = candidate_k = 15
        │   适配器：允许集合为空 → 本地 no_match（禁止退化为整库搜索）
        │           knowledge_id 后过滤兜底 · unsolved 工单排后
        │           候选正文 ≤ 4000 字（展示摘要仍 400 字）
        ▼
S1 同库多变体 RRF 合并 rrf_merge
        │
        ▼
重排 gte-rerank-v2                    [rerank=false]
        │   输入 = 标题 + 命中正文，看得到全部 15 条候选
        ▼
interleave_kbs 跨库按库内名次交错  ──┐
                                      ├── + 本地故障卡 fc_evidence
        ┌─────────────────────────────┘
        ▼
充分性评估 grade                      [grade.enabled 或 query_rewrite.enabled]
        │   只标记 relevant / irrelevant / unsure，不删候选
        │   coverage ∈ sufficient | insufficient | none | unknown
        │   未解决工单不能单独判 sufficient
        │
        ├── sufficient ────────────────────────────────┐
        │                                              │
        └── insufficient / none / unknown / 未启用      │
                │                                      │
                ▼                                      │
        名额未用 且 剩余预算够 且 两库状态正常?          │
                │                                      │
                ├── 图片有新观察 → 第二轮：query + observations
                ├── query_rewrite 开 → 第二轮：受控改写后检索
                └── 否 ────────────────────────────────┤
                │                                      │
                ▼                                      │
        _merge_rounds 按 evidence_id 去重               │
        合并 source_queries                             │
                │                                      │
                ▼                                      ▼
        select_hits + pack_hits（证据选择层）
          轮次升序交错（二轮保证拿到名额，但不插到首轮首条之前）
          反证至少留 1 席 · final_k=12 · 总 5000 字 · 单条 800 字
                │
                ▼
        S4 父块扩展 expand_parents     [parent_expand=false]
          围绕命中取窗口，不再只截父块开头
                │
                ▼
        synthesize（只在允许计划里排序）
          plan_id 越界 / 零证据 → 丢弃；全丢 → standard_flow
                │
                ▼
        guide：发布 plans.yaml 已审核原文
          match_anchor 认出真正支撑这一步的那条命中；认不出退回本地发布

  旁路：SSE evidence 事件发的是**全部候选**（实测 29 条），
        进模型的是 select_hits 选中的 12 条 —— 两者不是同一个集合。
```

### 仍未解决

- `leak 4/4`：WeKnora 融合分 ≈ `1/(60+rank)` 没有绝对含义，无法设阈值。本轮没有引入
  基于 rerank relevance 的闸门（用 2026-09-13 的 `B_rerank` 报告重算：真实样例中位
  0.853、leak 样例最高 0.549，阈值 0.55 可挡住全部 5 条 leak，代价是 6/42 误降级，
  且误降级集中在「口语」与「精确词」两类）。数据是旧语料，启用前须在当前语料重测。
- 精确词直查：`diagnose/expand.py` 的 `PRECISE_TOKENS` / `precise_tokens_in()` 仍只有
  单测引用，生产代码零调用点。
- 评测口径改动（`chunk_hit` 只认金标命中、按模型可见正文判定）使新数字与
  `reports/retrieval/` 历史报告不可比；开关决策前须重跑基线，且评测集
  `annotated_count` 仍是 2/58。

### 图的形式

本目录后续的流程图一律用 ASCII：Claude Code 对话区渲染不了 ```mermaid，提交后 diff
也更可读。`design.md` 里已有的 mermaid 块保持原样不改（append-only）。
