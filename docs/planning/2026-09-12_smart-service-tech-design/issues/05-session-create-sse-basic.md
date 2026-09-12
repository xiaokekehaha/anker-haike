# 05: 会话创建与 SSE 基础流

**What to build:** 用户新建会话并发送一条文本，服务端启动一个只有占位节点的 LangGraph 图（PostgresSaver 持久化），以 SSE 返回 run_started → progress → ping → done。每条事件先写入事件日志再发送，seq 单调递增。

**Blocked by:** 03（contracts 包：事件 / 动作 / 快照 Pydantic 模型与 JSON Schema）

**Status:** done（2026-09-12）

- [x] 新建会话返回 session_id 与 version=0（`POST /sessions` → 201）
- [x] 发消息返回 text/event-stream，事件顺序与契约一致，每 5 s 有 ping，流末尾必有 done（每条事件过 haike_contracts 校验；本机连真实 Postgres 实测 run_started → progress → ping → progress → ping → done）
- [x] 事件日志表中每条事件与发送内容一致，seq 连续（session_events 先写后发；多轮 seq 接续，实测 1–12 跨两个 run）
- [x] 异常路径发 error 后仍以 done(reason=error) 结束（节点异常 → error(node_failed)；超 deadline → error(deadline_exceeded, recoverable)；done 在 finally 中落库）
- [x] 同一会话并发第二次发消息被拒绝或排队，不产生两个 active run（sessions.active_run_id 条件更新原子占用；第二条返回 409 run_active 附最小快照；5 并发抢占只有 1 个成功）

**设计依据：** 08 §2、§5；03 §6

**实现记录（2026-09-12，Claude Code A）：** `orchestrator/app/sessions/`——store.py（sessions 投影表 + session_events 事件日志，Postgres 与内存两实现同语义）、graph.py（intake → reply 占位图，节点用 get_stream_writer 发 progress）、runner.py（run 事件流：deadline、ping、error → done）、sse.py（id=seq / event=type / data=JSON）、router.py（POST /sessions、POST /sessions/{id}/messages multipart `text`）、runtime.py（连接池 + AsyncPostgresSaver，库不可用时 sessions 接口 503 而非启动失败）。orchestrator 依赖新增 langgraph、langgraph-checkpoint-postgres、python-multipart、haike-contracts（本地 editable，Dockerfile 增加 `COPY contracts /contracts`）。测试：tests/test_sessions_api.py 9 项（内存存储）、tests/test_sessions_store_pg.py 2 项（真实 Postgres，可连时运行）。

**与票面 / 设计的差异：** version 在本票按「每个 run 结束 +1」推进，08 §2 要求的「每次 checkpoint 提交 +1」留到票 07 随快照一起实现；`updates` 流模式已接入只记日志。图片上传字段（purpose=fault / receipt）留给票 29。
