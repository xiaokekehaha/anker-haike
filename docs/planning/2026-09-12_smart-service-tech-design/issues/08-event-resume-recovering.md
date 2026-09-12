# 08: 事件续接与前端恢复态

**What to build:** 页面刷新或断流后，前端先读快照，若 active_run 未过 deadline 则调用续接接口，服务端先重放事件日志再接实时流；否则按 pending_input 回到对应状态。

**Blocked by:** 06（前端 reducer、SSE 解析与 ProgressBar）、07（快照接口与 sessions 投影表）

**Status:** ready-for-agent

- [ ] 续接接口先返回 after_seq 之后的历史事件，再无缝接实时事件，不重复不丢失
- [ ] 前端进入 recovering 态后按契约 §6 五条规则落到 streaming / awaiting_input / idle
- [ ] 超过 run_started.deadline_ms + 5 s 无事件判定断流并自动恢复
- [ ] 本地状态与快照冲突时以快照为准（有测试）
- [ ] 服务重启后正在等待的会话刷新页面可恢复

**设计依据：** 08 §6、§8；05 §5
