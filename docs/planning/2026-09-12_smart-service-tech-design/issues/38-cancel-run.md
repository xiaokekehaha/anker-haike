# 38: 取消 run

**What to build:** POST /cancel 设置取消标志，图在下一节点边界停止，发 done(cancelled) 并持久化 cancelled_run；pending_input 保留；前端 streaming / tool_running 时可点取消，随后 abort fetch；仅 abort 不等于取消。

**Blocked by:** 08（事件续接与前端恢复态）

**Owner:** Claude Code A（后端；第三项「真实模型流被中止」随票 13 后端完成后由 A 补验证）

**Status:** done（2026-09-12；后端既有实测，Codex 补齐前端取消与恢复）

- [x] 取消后快照含 cancelled_run，pending_input 与取消前一致（fold_timeline 已按 08 §7 保留取消前 pending；测试含构造的 awaiting_input 上一轮）
- [x] 前端仅断开连接时 run 继续跑到完成，快照可读到结果（票 08 RunManager 保证；uvicorn 实测 1 s 断开后 run 跑到 done(completed)）
- [x] 取消中的模型调用被中止不再计费重试（tests/test_sessions_cancel_stream.py：慢流假模型收到 CancelledError 且未跑完、主模型只调 1 次、备用模型 0 次、无 error 事件、无 completed 的 message_end、done(cancelled)；ModelRouter.stream 只捕获 Exception，CancelledError 直达）

**设计依据：** 08 §7；05 §6

**后端实现记录（2026-09-12，Claude Code A）：** `POST /sessions/{id}/cancel` body `{run_id}` → `{run_id, status: cancelled | cancelling}`；run 不属于该会话或已结束 → 409 `run_not_active` 附快照。RunManager.cancel 置位 run 的 cancel_event 并等待收尾（最多 5 s）；runner 里 watcher 把事件转成队列哨兵，命中后 cancel 图任务、等其退出，再以 checkpoint 推导 version 写 done(cancelled)。「在下一节点边界停止」的落地语义：被中止节点的部分工作丢弃，状态停在上一个已提交 checkpoint（测试：intake 完成、reply 睡眠中取消 → stage=intake、next=('reply',)、用户消息保留）。测试 tests/test_sessions_cancel.py 6 项。

- [x] 前端取消按钮接入 /cancel，终止本地请求并按快照恢复 pending；取消接口失败显示错误，保留 run 信息供再次恢复。
- [x] 页面卸载/reset 只 abort 本地请求，不误发 /cancel；迟到流事件不会覆盖新会话。

**前端验证（Codex）：** useSession 的模拟 HTTP/SSE 测试覆盖服务端取消请求体、流 reader.cancel、取消后待输入恢复、取消失败、卸载仅断流。本轮没有调用真实模型或重新执行后端取消演练。
