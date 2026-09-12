# 38: 取消 run

**What to build:** POST /cancel 设置取消标志，图在下一节点边界停止，发 done(cancelled) 并持久化 cancelled_run；pending_input 保留；前端 streaming / tool_running 时可点取消，随后 abort fetch；仅 abort 不等于取消。

**Blocked by:** 08（事件续接与前端恢复态）

**Status:** ready-for-agent

- [ ] 取消后快照含 cancelled_run，pending_input 与取消前一致
- [ ] 前端仅断开连接时 run 继续跑到完成，快照可读到结果
- [ ] 取消中的模型调用被中止不再计费重试

**设计依据：** 08 §7；05 §6
