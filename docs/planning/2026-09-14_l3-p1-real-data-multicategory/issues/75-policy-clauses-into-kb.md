# 75: 政策条款入知识库 kb_policy（仅供咨询引用）

**What to build:** `haike-kb ingest-policy`：把 `clauses.yaml` 按 policy 生成 Markdown（front-matter：doc_id=policy_<id>、scope=category_generic、region_list、channel_list、policy_version、publish_state）导入 WeKnora 新库 `kb_policy`；`knowledge/search.py` 增第三库，仅在意图 ∈ {warranty_query, explain(政策类)} 时参与；回答引用条款 id 并链接 clauses；判定仍只走引擎（断言 propose / authorize 不读检索结果）。

**Blocked by:** 74, 70

**Status:** todo

**Owner:** —

- [ ] 「你们的保修政策是什么」→ 引用 kb_policy 片段 + clause_id；排障问题零 kb_policy 召回
- [ ] 政策更新后 policy_version 变化 → 旧条款 withdrawn、新条款 published
- [ ] 引擎判定路径不依赖 WeKnora 可用性（unavailable 时仍可判）

**设计依据：** 04 §6
