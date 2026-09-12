# 07: 快照接口与 sessions 投影表

**What to build:** 提供会话权威快照接口：从 checkpoint 与事件日志派生 version、stage、active_run、pending_input，并把事件日志折叠成 timeline。sessions 投影表可丢弃后重建。

**Blocked by:** 05（会话创建与 SSE 基础流）

**Status:** ready-for-agent

- [ ] 快照字段与契约 §6 一致
- [ ] timeline 由事件日志按 seq 重放折叠：消息合并为完整文本、卡片带用户已选结果、工具行保留
- [ ] 删除投影表后调用重建命令，快照结果与删除前一致
- [ ] 业务逻辑不直接读投影表（代码审查项）

**设计依据：** 08 §2、§6
