# 27: KnowledgeAdapter：scope → knowledge_ids 与四态结果

**What to build:** 实现 hybrid_search(kb, query, top_k, scope)：启动时拉取全部 knowledge 元数据建索引；confirmed_sku / category_only 映射为允许集合；空集合直接 no_match 不发请求；请求带 knowledge_ids（IV-1：锁定镜像后核对参数名，不支持则后过滤并 top_k×3）；返回 ok / no_match / unavailable，单次 ≤ 2k token 截断，unsolved 工单标 counter_evidence。

**Blocked by:** 24（product_state 三分与追问上限 R7）、26（WeKnora 独立 tenant 与知识库入库）

**Status:** ready-for-agent

- [ ] IV-1 核对结论写入 findings.md，适配器按结论实现
- [ ] category_only 检索结果不含 scope=sku 的条目（测试）
- [ ] 允许集合为空时无网络请求发出
- [ ] WeKnora 停掉时返回 unavailable 且带模型可读 hint
- [ ] 超长结果截断并标 truncated

**设计依据：** 09 §2.3、§2.4、§4；07 §14；03 §2.3
