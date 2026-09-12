# 26: WeKnora 独立 tenant 与知识库入库

**What to build:** 为项目建独立 tenant 与 API key；kb_manual（2 份说明书 PDF、约 50 条 FAQ、1 份排障手册）与 kb_tickets（约 200 条工单 CSV）的模拟数据与导入脚本，每条带 scope / sku_list / category / doc_version / result 元数据；Embedding 与 Rerank 配置为百炼远程 API；导出快照脚本。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** ready-for-agent

- [ ] 导入脚本可重复执行，元数据在 WeKnora 中可查
- [ ] 父子分块 800 / 200 字，BM25 + 向量开启，图谱关闭
- [ ] Embedding 维度 1024 与 pgvector 配置一致，kb_ver 记录绑定的 embedding 模型
- [ ] Rerank 远程不可用时检索仍返回结果并记录
- [ ] 导出 / 导入快照脚本可回滚知识库

**设计依据：** 03 §3.2；09 §2.2；model-selection §2
