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

## 票 38 取消
- LangGraph 没有「节点边界取消」原语；取消 asyncio 任务会中断当前节点，状态停在上一个 checkpoint。这与 08 §7 的意图一致（部分工作丢弃、可继续），但意味着 apply_action 这类有副作用的节点必须以 action_id 幂等（08 §3 已要求），否则取消恰好落在副作用之后、checkpoint 之前会重放副作用。
- 票 13/14 接 ModelRouter 时：CancelledError 必须直接向上抛，不能进入重试链，否则「取消不再计费重试」不成立。
- 手测脚本里 `wait` 不带参数会等 nohup 的服务进程，导致误判卡死；后续脚本记录后台 curl 的 pid 单独 wait。

## 票 20 三段式等待
- LangGraph 中断语义（实测）：prepare 节点只执行一次；含 interrupt 的节点在恢复时从头重跑并重发自定义事件；`interrupt()` 所在节点的 checkpoint 不提交，中断后 metadata.step 停在上一节点；节点内 `get_config()["metadata"]["langgraph_step"]` 等于中断后推导出的 version。
- AsyncPostgresSaver 的 checkpoint 写入相对 astream 的 updates 流是异步的：在收到 `__interrupt__` 那一刻 `aget_state` 可能还是上一个 checkpoint。凡是「事件里的 version 必须等于 run 结束的 version」的场景，version 要在节点内确定并随载荷带出，不能在运行器中途查库。内存 saver 测不出这类竞态，数据库相关票必须带真实 saver 的测试。
- 图结构一变（加节点），依赖 progress 序列 / version 数值的测试全部要改，包括其他会话的测试（B 的 test_rules）。约定：改 graph.py 的人负责同步跑全量后端测试并修期望；后续测试尽量断言相对关系而非绝对 version。
