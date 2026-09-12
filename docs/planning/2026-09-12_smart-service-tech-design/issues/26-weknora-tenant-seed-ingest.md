# 26: WeKnora 独立 tenant 与知识库入库

**What to build:** 为项目建独立 tenant 与 API key；kb_manual（2 份说明书 PDF、约 50 条 FAQ、1 份排障手册）与 kb_tickets（约 200 条工单 CSV）的模拟数据与导入脚本，每条带 scope / sku_list / category / doc_version / result 元数据；Embedding 与 Rerank 配置为百炼远程 API；导出快照脚本。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done（2026-09-12，本机 WeKnora 实测）

**Owner:** Claude Code B（2026-09-12 认领；改动范围 `orchestrator/app/knowledge/`、`data/knowledge/`、`deploy/weknora/`；实时验证需 DASHSCOPE_API_KEY 与 tenant API key）

- [x] 导入脚本可重复执行，元数据在 WeKnora 中可查（`make kb-ingest`：知识库按名复用；文档按 title + doc_version 幂等，版本变更删旧建新；元数据写 `custom_metadata`；工单 CSV 每行一条知识；FAQ replace 模式整体覆盖。内存版 WeKnora 测试：二次导入 0 新建 / 203 跳过。本机实测：3 手册 + 200 工单 parse_status 全部 completed，`make kb-verify` 可见 custom_metadata；第 2 / 3 次导入 created=0）
- [x] 父子分块 800 / 200 字，BM25 + 向量开启，图谱关闭（建库 `chunking_config.enable_parent_child=true, parent_chunk_size=800, child_chunk_size=200`；混合检索为 WeKnora 默认；不设图谱配置。单位为字符，非 token）
- [x] Embedding 维度 1024 与 pgvector 配置一致，kb_ver 记录绑定的 embedding 模型（`deploy/weknora/builtin_models.yaml` 登记百炼 text-embedding-v4 · 1024 维并挂载到 weknora-app；导入时校验模型维度 ≠ 1024 即报错；manifest `kb_ver = <doc_version>+<embedding 模型名>`。无百炼 key 时用 `deploy/dev/embedding_stub.py`（确定性 1024 维桩）登记为 Embedding 模型跑通全链路，manifest kb_ver=2026-09-12.1+stub-embedding-1024；切百炼只需设 EMBEDDING_* 变量重跑 ingest）
- [x] Rerank 远程不可用时检索仍返回结果并记录（v0.8.0 中 rerank 绑定在问答会话而非知识库，`knowledge-search` / `hybrid-search` 不经 rerank；问答链 rerank 失败回退召回结果（官方 rerank.go）。builtin_models 用 aliyun 协议登记 gte-rerank-v2；qwen3-rerank 的 /reranks 路径与 WeKnora generic 的 /rerank 不兼容，记入 findings）
- [x] 导出 / 导入快照脚本可回滚知识库（`make kb-snapshot` 导出源文件 + manifest + 远端清单到 data/knowledge/snapshots/<时间戳>/；`make kb-snapshot DIR=…` 用快照重新幂等导入并清理快照外条目。测试：误加一条、误删一条后导入快照恢复到 203 条）

**设计依据：** 03 §3.2；09 §2.2；model-selection §2

**实现记录（2026-09-12，Claude Code B）：** 数据 `data/knowledge/`（kb_manual：两份说明书节选 + 排障手册 Markdown 带 front-matter 元数据、faq_rv.yaml 50 条；kb_tickets：`scripts/gen_tickets.py` 确定性生成 200 条 CSV，solved / unsolved / escalated 三类）；`orchestrator/app/knowledge/`（weknora_client.py 按 v0.8.0 docs/api 封装、ingest.py、snapshot.py、cli.py `haike-kb`）；`deploy/weknora/builtin_models.yaml` + docker-compose 挂载与 `BUILTIN_MODELS_CONFIG`；`.env.example` 补 EMBEDDING / RERANK / WEKNORA_TENANT_PASSWORD；models.yaml 填 embed-primary=text-embedding-v4、rerank-primary=gte-rerank-v2。tests/test_knowledge_ingest.py 11 项（httpx MockTransport 内存版 WeKnora）。

**与票面差异：** 说明书用 Markdown 在线文本入库而非 PDF 上传（客户端保留 `upload_file` 走 file 接口，需要 PDF 时可直接改用）；工单不用 WeKnora 原生 CSV 上传（会整表变一份文档），改为每行一条 manual 知识。

**本机实测记录（2026-09-12）：** `make kb-bootstrap` 自助注册 tenant 10001（用户 haike-orchestrator），登录响应无 data 包装、tenant 在 `active_tenant`、注册不返回 api_key；改为 `POST /tenants/{id}/api-keys`（受限 key 必须带 capabilities；`full_access=true` 的全权限 key 才能管模型），key 写入 .env。WeKnora 对远程模型地址有 SSRF 白名单，compose 增加 `SSRF_WHITELIST_EXTRA`（本机填 host.docker.internal）。manual 知识 `status` 只接受 draft / publish；`custom_metadata` 只接受标量，sku_list 改逗号串。FAQ 列表 data 为 {data, total, page, page_size}。快照已导出到 data/knowledge/snapshots/。已知：FAQ 条目计数为 52（50 条 replace 后稳定不增长），待票 33 前核对是否含相似问计入。
