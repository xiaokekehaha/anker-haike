# 08: 事件续接与前端恢复态

**What to build:** 页面刷新或断流后，前端先读快照，若 active_run 未过 deadline 则调用续接接口，服务端先重放事件日志再接实时流；否则按 pending_input 回到对应状态。

**Blocked by:** 06（前端 reducer、SSE 解析与 ProgressBar）、07（快照接口与 sessions 投影表）

**Status:** done（2026-09-12；后端既有实测，Codex 补齐前端恢复与生命周期回归）

- [x] 续接接口先返回 after_seq 之后的历史事件，再无缝接实时事件，不重复不丢失（`GET /sessions/{id}/runs/{run_id}/events?after_seq=`，也接受 Last-Event-ID 头；先订阅再读历史、按 seq 去重；真实 Postgres 实测断开后续接 2→3→4 done）
- [x] 前端进入 recovering 态后按契约 §6 五条规则落到 streaming / awaiting_input / idle
- [x] 超过 run_started.deadline_ms + 5 s 无事件判定断流并自动恢复
- [x] 本地状态与快照冲突时以快照为准（有测试）
- [x] 服务重启后正在等待的会话刷新页面可恢复（后端已就位：启动时 reconcile 孤儿 run 补 error(server_restarted) → done(error) 并释放 active_run，快照恢复为可继续；kill -9 实测通过。前端已通过持久化 session_id 加载快照、空 active_run / pending_input 恢复测试）

**设计依据：** 08 §6、§8；05 §5

**后端实现记录（2026-09-12，Claude Code A）：** `app/sessions/manager.py` RunManager——run 在后台任务执行并向订阅者广播，POST /messages 的响应只是 after_seq=0 的订阅者，因此断开连接不再中止 run（08 §7「abort 不等于取消」）；`subscribe` 先订阅再读 session_events 重放，再接实时并以 seq 过滤重复；`reconcile_orphans` 在启动时把投影表里仍 active 但本进程没有在跑的 run 收尾。router 新增续接接口与 404 run_not_found；store 新增 list_active_runs。测试 tests/test_sessions_resume.py 6 项。限制：广播在进程内存中，单副本 orchestrator 可用；多副本需换 Redis pub/sub（票 46 / 49 前评估）。前端 recovering 态、deadline + 5 s 断流判定、本地状态与快照冲突测试属前端部分。

**前端接续（Codex，2026-09-12）：** `useSession.test.tsx` 覆盖页面刷新、pending/idle/expired active run、断流先快照再续接、15 s 提示与 deadline+5 s、网络失败保留会话、404 清理、StrictMode、reset/unmount 防迟到回写。快照没有 seq，因此当前 run 从 0 重放，reducer 按 seq 去重且保留快照 deadline；done 后重取快照同步已消费卡片。重连上限 3 次，失败可手动恢复。前端采用模拟 HTTP/SSE 验证，本轮没有重做后端 kill -9 实测。
