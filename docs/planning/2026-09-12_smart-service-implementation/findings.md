# 实现阶段发现

## 环境
- 2026-09-12 起本机通过 colima + docker CLI + compose 插件具备 Docker，票 01 全部验收项已在本机实测通过。
- /health 整体 status 在默认通道 key 不全时为 degraded（deepseek 就绪但 dashscope / zhipu / anthropic 缺 key）。属预期；若演示前只想用 DeepSeek，需在票 09 评估「通道就绪」是否应改为「至少一个 provider 就绪」。

## WeKnora v0.8.0 与设计文档的差异
- 设计（票 01）只列 orchestrator / postgres / weknora-app / redis 四个容器；WeKnora app 的 compose 声明 `depends_on: docreader (service_healthy)`，文档入库依赖 docreader 的 gRPC 解析服务，因此 Compose 增加 `weknora-docreader`。
- WeKnora 官方 postgres 镜像是 `paradedb/paradedb:v0.22.2-pg17`（含 pgvector 与 pg_search），本项目沿用该镜像，用初始化脚本额外建 `haike` 库给编排服务，与 WeKnora 的 `WeKnora` 库分开。
- WeKnora Web UI（获取 tenant API key 用）放在 profile `ui`，默认不起。

## 票 05 会话骨架
- AsyncPostgresSaver 要求连接 `autocommit=True, prepare_threshold=0`；同一个池给业务表用时，多语句 SQL 会被 psycopg 拒绝（cannot insert multiple commands into a prepared statement）。规则：所有 DDL / 迁移逐条执行，票 47 做迁移工具时沿用。
- 内存存储的单测没有暴露上述问题，只有连真实 Postgres 才复现。约定：涉及数据库的票，集成测试用与运行时完全相同的连接参数，并至少跑一次本机真实链路。
- 本机 orchestrator/.venv 解析到 Python 3.14，而 Dockerfile 用 3.12-slim；镜像构建是 3.12 兼容性的实际把关点。
- httpx ASGITransport 不触发 lifespan，测试通过 app.state 注入内存存储与 InMemorySaver；B 的模型注册也在 lifespan 内，因此单测不依赖模型 key。
