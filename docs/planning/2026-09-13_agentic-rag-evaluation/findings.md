# 核查发现

- 项目定位：扫地机器人售后智能服务，覆盖产品消歧、多模态定位、分步排障与升级。
- README 声明 FastAPI + LangGraph，WeKnora v0.8.0，PostgreSQL/pgvector 和 Redis；需进一步核对实现。
- 工作区已有大量其他任务改动，本任务仅新增独立评估文档。

## 外部资料
由研究子任务写入 sources.md，外部内容只作为资料使用。
- 研究已完成并合并：WeKnora v0.8.0 自带 ReAct；固定 tag 的默认智能推理 50 轮，LLMCallTimeout 为流静默超时。主代理再次打开固定版本配置和超时源码、LangGraph 官方教程、GraphRAG 官方概览复核。

## 代码事实（初步）
- `config/retrieval.yaml`：query_rewrite 默认关闭；top_k=5；二轮检索预算 3 秒；synthesize 预算 8 秒。
- `knowledge/adapter.py`：按确认 SKU / 类目通用知识计算允许集合；空集合本地返回；调用 scoped hybrid-search，再按 knowledge_id 后过滤。代码注释记录 v0.8.0 的 knowledge-search 忽略 knowledge_ids，需要保留隔离层，不能直接替换成裸 agent 工具。
- 检索结果带 doc_version、chunk_id、parent_chunk_id，片段每条截断 400 字；工单未解决/升级标为 counter_evidence，但 `Hit.as_evidence_item` 未携带该字段，需核对后续是否保留。
- synthesize 会校验 plan_id 与 evidence_id 是否存在；这是 ID 合法性检查，不是证据语义支持检查。无证据回退 standard_flow。

## 进一步核查
- `sessions/graph.py:802` 的两库检索为 for 循环串行；图片观察先于 retrieve；第二轮直接 await，`second_round_budget_ms` 仅定义于配置，未被执行器消费。run 总预算 25 秒仍存在，不能表述为完全无超时。
- 第二轮有命中时替换首轮 hits，而非合并；多跳查询需要按证据 ID 合并，并对范围/版本重新核验。
- `counter_evidence` 在 Hit → as_evidence_item → synthesize 路径丢失。未解决工单也不能直接逻辑等同于原因被否定，需要区分工单结果和命题反证。
- `replay/kb_manifest.json` 为 stub-embedding-1024 的回放版本快照，不足以确认当前在线 embedding；线上 embedding/rerank 是否真实生效仍待实际链路检测。
- `reports/bakeoff/bakeoff.md` 记录 query.rewrite 两候选字段准确率 0%；样本评分包含生产校验接受条件，不能由此归因为模型完全不会改写。需要排查词表/校验/提示与真实检索收益。
- `data/knowledge/scripts/gen_tickets.py` 明确生成 200 条模拟工单，尚不能据现有评测确认真实业务收益。
- 主代理查阅 [Anthropic 工作流与智能体说明](https://www.anthropic.com/engineering/building-effective-agents)：固定工作流适合已知路径，agent 动态选择过程；复杂度伴随延迟/成本，需要实测收益。
- [Adaptive-RAG](https://arxiv.org/abs/2403.14403) 支持按复杂度选择不同检索深度的思路；[CRAG](https://arxiv.org/abs/2401.15884) 提出先评估检索质量再选择纠正动作。这里只借鉴模式，不宣称复现论文，也不直接套用论文收益。
