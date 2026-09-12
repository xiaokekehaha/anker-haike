# 27: KnowledgeAdapter：scope → knowledge_ids 与四态结果

**What to build:** 实现 hybrid_search(kb, query, top_k, scope)：启动时拉取全部 knowledge 元数据建索引；confirmed_sku / category_only 映射为允许集合；空集合直接 no_match 不发请求；请求带 knowledge_ids（IV-1：锁定镜像后核对参数名，不支持则后过滤并 top_k×3）；返回 ok / no_match / unavailable，单次 ≤ 2k token 截断，unsolved 工单标 counter_evidence。

**Blocked by:** 24（product_state 三分与追问上限 R7）、26（WeKnora 独立 tenant 与知识库入库）

**Status:** done（2026-09-12；票 24 的 product_state 三分尚未落地，适配器以 KnowledgeScope 入参承接，24 完成后直接接入）

**Owner:** Claude Code B（`orchestrator/app/knowledge/adapter.py`）

- [x] IV-1 核对结论写入 findings.md，适配器按结论实现（`/knowledge-search` 忽略 knowledge_ids，`/knowledge-bases/{id}/hybrid-search` 遵守；空列表等于不过滤 → 本地空集合直接 no_match；适配器走 hybrid-search + match_count×3 + 按 knowledge_id 后过滤兜底）
- [x] category_only 检索结果不含 scope=sku 的条目（测试）（内存版 + 本机 WeKnora 真实检索均只返回 troubleshooting_rv；服务端泄漏 knowledge_ids 时后过滤兜底另有测试）
- [x] 允许集合为空时无网络请求发出（unknown / 品类不匹配 / 工单库 category_only 三种情形断言请求数不变）
- [x] WeKnora 停掉时返回 unavailable 且带模型可读 hint（ConnectError / 超时 / 5xx / 401–404 → unavailable，`for_model()` 只给 status + hint）
- [x] 超长结果截断并标 truncated（默认 2000 字符 ≈ 2k token，单条 snippet ≤ 400 字）

**设计依据：** 09 §2.3、§2.4、§4；07 §14；03 §2.3

**实现记录（2026-09-12，Claude Code B）：** `app/knowledge/adapter.py`：`KnowledgeScope{product_state, category, sku}`、`refresh_index()` 拉取两库 knowledge 元数据（custom_metadata 为 dict，命中里的 knowledge_custom_metadata 为 YAML 文本，统一 `parse_custom_metadata`）、`allowed_entries()` 按 09 §2.3 映射、`hybrid_search()` 四态、unsolved / escalated 工单标 counter_evidence 并排后、`Hit.as_evidence_item()` 对应契约 evidence.items。evidence_id = WeKnora chunk id（稳定）。tests/test_knowledge_adapter.py 11 项（含本机集成）。tool_call / evidence 事件与 EvidenceDrawer 在票 28。
