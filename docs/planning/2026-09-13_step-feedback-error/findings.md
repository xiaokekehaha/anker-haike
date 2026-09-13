# 排查结论

截图对应会话 `d99223bb05244f7a8c254fe2136f78bc`；Chrome 当前页面内容与该会话 HTTP 快照一致。

## 原因

1. 历史真实故障：北京时间 2026-09-13 08:33:21（更早 09-12 23:42:07 也发生过），数据库 session_events seq=7 记录 `node_failed` / `RulesError`。旧服务 RulesConfig 不接受 `/srv/config/rules/safety_terms.yaml` 中的 `pre_step` 字段，Pydantic 报 `extra_forbidden`。
2. 当前误报：08:57 首轮已正常生成步骤卡；09:01:04 / 09:01:14 / 09:01:18 三次反馈都以 `done(reason=awaiting_input)` 正常结束，无新增 error。当前 version=19，等待“检查滤网是否需要更换”卡片反馈。
3. 后端 `orchestrator/app/sessions/snapshot.py:202` 从所有历史事件提取 last_error，在后续成功运行后不清理。前端 `useSession.ts:203` 成功反馈后拉快照，`reducer.ts:156` 把历史 last_error 重新变为当前错误，并将 message 设为空、recoverable 设为 true；App 默认文案因此显示“出现了一个错误，可以稍后重试”。
4. 截图中当前“检查滤网是否需要更换”的卡片尚未被服务器记录为已反馈。不能将截图圈出的按钮直接认定为后端新失败；可确认的是页面当前弹窗对应旧错误残留。

## 日志证据

- 本项目 PostgreSQL `haike.session_events`（数据库 haike，表 session_events），按 session_id 过滤可查错误原文及后续成功事件。
- `session-event-evidence.jsonl`：本次导出的相关 run_started / error / done 事件。
- `logs/events.jsonl:1328`、`:1336`、`:1343`：三次步骤反馈的正常终止事件。
- Docker 访问日志：`docker compose logs --since 30m orchestrator`，相应 actions 请求返回 200。
- JSONL 配置为每份 10 MB，保留 3 份轮转，Docker 挂载 `./logs:/srv/logs`。

## 复现与范围

`python3 docs/planning/2026-09-13_step-feedback-error/repro_snapshot.py` 已运行；只读 HTTP 查询，约 0.09 秒，断言失败确认成功推进后的快照仍包含 08:33 旧错误。浏览器只读观察也看到相同通用 toast。

本次用户要求原因与日志，故诊断流程止于日志核验和只读复现，未执行修复、部署或改写用户会话。建议后续将“当前可展示错误”限定为最近未恢复的运行，保留历史错误供审计，并补充“先失败、后成功、恢复快照”的回归验证。
