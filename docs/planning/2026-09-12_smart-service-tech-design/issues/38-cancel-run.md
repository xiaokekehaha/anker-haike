# 38: 取消 run

**What to build:** POST /cancel 设置取消标志，图在下一节点边界停止，发 done(cancelled) 并持久化 cancelled_run；pending_input 保留；前端 streaming / tool_running 时可点取消，随后 abort fetch；仅 abort 不等于取消。

**Blocked by:** 08（事件续接与前端恢复态）

**Status:** in-progress（2026-09-12 后端 done；前端「取消按钮 + abort」待 Codex 随票 06/08 前端部分接）

- [x] 取消后快照含 cancelled_run，pending_input 与取消前一致（fold_timeline 已按 08 §7 保留取消前 pending；测试含构造的 awaiting_input 上一轮）
- [x] 前端仅断开连接时 run 继续跑到完成，快照可读到结果（票 08 RunManager 保证；uvicorn 实测 1 s 断开后 run 跑到 done(completed)）
- [ ] 取消中的模型调用被中止不再计费重试（机制已就位：取消即 cancel 图任务，节点内 await 收到 CancelledError，占位节点 sleep 实测 0.03 s 中止；真实模型调用的中止待票 13/14 接入 ModelRouter 后验证，ModelRouter 需把 CancelledError 视为终止而非可重试错误）

**设计依据：** 08 §7；05 §6

**后端实现记录（2026-09-12，Claude Code A）：** `POST /sessions/{id}/cancel` body `{run_id}` → `{run_id, status: cancelled | cancelling}`；run 不属于该会话或已结束 → 409 `run_not_active` 附快照。RunManager.cancel 置位 run 的 cancel_event 并等待收尾（最多 5 s）；runner 里 watcher 把事件转成队列哨兵，命中后 cancel 图任务、等其退出，再以 checkpoint 推导 version 写 done(cancelled)。「在下一节点边界停止」的落地语义：被中止节点的部分工作丢弃，状态停在上一个已提交 checkpoint（测试：intake 完成、reply 睡眠中取消 → stage=intake、next=('reply',)、用户消息保留）。测试 tests/test_sessions_cancel.py 6 项。
