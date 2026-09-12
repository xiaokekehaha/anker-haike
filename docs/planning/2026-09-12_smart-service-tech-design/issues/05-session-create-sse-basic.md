# 05: 会话创建与 SSE 基础流

**What to build:** 用户新建会话并发送一条文本，服务端启动一个只有占位节点的 LangGraph 图（PostgresSaver 持久化），以 SSE 返回 run_started → progress → ping → done。每条事件先写入事件日志再发送，seq 单调递增。

**Blocked by:** 03（contracts 包：事件 / 动作 / 快照 Pydantic 模型与 JSON Schema）

**Status:** ready-for-agent

- [ ] 新建会话返回 session_id 与 version=0
- [ ] 发消息返回 text/event-stream，事件顺序与契约一致，每 5 s 有 ping，流末尾必有 done
- [ ] 事件日志表中每条事件与发送内容一致，seq 连续
- [ ] 异常路径发 error 后仍以 done(reason=error) 结束
- [ ] 同一会话并发第二次发消息被拒绝或排队，不产生两个 active run

**设计依据：** 08 §2、§5；03 §6
