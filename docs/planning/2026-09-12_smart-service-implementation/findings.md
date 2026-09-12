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

## 票 07 快照与投影
- LangGraph checkpoint metadata.step 在同一 thread 上跨 run 单调递增（含输入 checkpoint 的 step -1 起算），可直接作为契约 version 的来源，无需自维护计数器。异常 run 仍会写入输入 checkpoint，version 会 +1。
- session_events 一开始外键到 sessions 并级联删除，与「投影表可丢弃后重建」矛盾；已去掉外键。规则：事件日志与 checkpoint 不得依赖任何投影表。
- 事件协议里没有用户消息事件，timeline 的 user_message 只能来自 checkpoint 状态；节点在写 messages 时必须带 run_id，否则无法定位到 timeline 位置。后续改图状态的票需保持这一约定。

## 票 08 续接
- 票 05 把 run 写成请求内的生成器，客户端断开会触发 finally 取消图任务，违反 08 §7；票 08 改为 RunManager 后台执行。规则：任何长任务不得与 HTTP 响应生命周期绑定。
- httpx ASGITransport 会把 SSE 响应整体收完再返回，不能模拟「收到首帧即断开」；断连 / 中途续接语义要直接驱动 RunManager 或在真实 uvicorn 上用 curl --max-time 验证。
- 实时广播在进程内存，orchestrator 目前单副本；多副本部署前需改 Redis pub/sub 或粘性路由，已在票 08 记录，票 46 / 49 评估。
