# 发现

- 本轮全部自动化回归通过：后端 452/452、前端 131/131、契约 62/62、codegen 6/6、contracts-check / ruff / build / db-check 均通过、stub 巡检 29/29。
- 真实服务六组场景（a1 / a2 / a3 / rediagnose / cancel / resume）全部通过；浏览器 A1 全流程通过，console error 为空。
- 模型直连探测实测：deepseek-flash 1171 ms、glm-4.7 1390 ms、glm-4.6v 327 ms 已连通；qwen-* 未配置跳过。5 分钟缓存在 curl 与弹窗间共享。
- 票 42 已完成智谱真实评测，models.yaml 升到 2026-09-13.2；但 diagnose.synthesize / reply.stream / escalate.summary / warranty.receipt_ocr 四个 task 仍无第二家达标备用位，query.rewrite 全部候选准确率 0%。
- 录制包在 09:12 被重录为 .2；在此之前 .1 的包与新配置不兼容，replay-verify 直接失败 —— 模型配置改版必须同步重录回放包。
- **新缺陷**：容器每次启动 `sessions.runtime session runtime unavailable: KeyError: 'seq'`。业务库有 4 条 run_started 事件 event_json 缺 seq（09-11/09-12 集成测试残留，run_id=r1），manager.py:153 直接 e["seq"] 抛异常，被 runtime.py:63 吞掉 → 票 08 的重启孤儿 run 收尾实际从未执行。
- 集成测试直写业务库 haike 且不清理，sessions 表残留一批 run-0 / run-b / run-active 的 active_run_id 行。
- 快照 last_error 残留缺陷仍在（snapshot.py:203 取全历史 + reducer.ts:156 当成当前错误且 message 为空），step-feedback-error 任务只诊断未修。
- 发布清单再次失真：RELEASE.md 与 bakeoff.md 抬头写 models.yaml 2026-09-13.1，实际 .2；RELEASE.md 镜像 tag 为 sync-085548，实际运行 haike/orchestrator:dev。
- /health 恒为 degraded（缺 dashscope/anthropic/google key），导致 health_check_failed 告警长期 active（streak 13），属持续误报；alerts.sinks 仍为空。
- 票 32 三处差异原样未动：vision→retrieve 串行（graph.py:380）、补检索无整轮 3 s 硬上限（graph.py:1031）、query_rewrite 仍 false（retrieval.yaml 2026-09-12.1）。
- 首轮 a3 的 RemoteProtocolError 是其他任务 09:19 重建容器所致，非产品缺陷；容器稳定后重跑通过。

## 修复回填（2026-09-13 10:20–10:35）

用户要求修 P1 KeyError 与快照 last_error 残留，两项均已改完并实测。

- `manager.py`：`reconcile_orphans` 拆出 `_finalize_orphan`，seq / run_id / type 改读事件表的列（`list_event_records`）而不是 `event_json`——既绕开缺字段，也保证 `last_seq` 是库里真实最大值不会撞唯一约束；单会话失败只跳过该会话并记 error 日志，不再中断整轮与启动流程。
- `snapshot.py`：错误改挂在所属 run 上（`run["error"]`，带 code / message / recoverable / at），收尾时只取最近一次 run 的错误；更早 run 的错误留在事件表供审计。
- `contracts`：`LastError` 增加 `message`（默认 ""）与 `recoverable`（默认 true），schema / TS / zod 已用 `make contracts` 重新生成。
- `reducer.ts`：restore 分支改用快照里的 message / recoverable，不再硬编码空文案 + recoverable=true。
- 新增测试：`test_last_error_only_from_latest_run`、`test_reconcile_orphans_tolerates_events_missing_seq`、reducer restore 的两条断言。

实测：
- 重新构建部署后首次启动日志为 `session runtime ready (orphan runs finalized: 26)`，`KeyError` 与 `session runtime unavailable` 均消失；再次重启为 `finalized: 0`，幂等。26 条积压的测试残留 active run 一次性收尾。
- 原问题会话 `d99223bb05244f7a8c254fe2136f78bc` 的快照 `last_error` 由 08:33 的旧 `RulesError` 变为 `null`；`docs/planning/2026-09-13_step-feedback-error/repro_snapshot.py` 由 AssertionError 转为 exit 0。
- 浏览器恢复该会话：步骤卡与历史正常渲染，不再弹「出现了一个错误」，console 无错误。
- 回归：后端 454/454、前端 132/132、契约 62/62、codegen 6/6、contracts-check / ruff / build 通过；巡检 29/29；回放 a1/a2/a3 三条 exit 0；真实六场景 6/6。
