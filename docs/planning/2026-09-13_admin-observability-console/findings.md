# 发现（2026-09-13 核对）

## 已验证的事实
- `build_graph(None).get_graph().to_json()` 可直接导出拓扑：21 节点（含 `__start__`/`__end__`）、46 条边，边带 `conditional` 标记。DAG 拓扑层无需手工维护。
- 运行器 `runner.run_message` 以 `stream_mode=["custom","updates"]` 消费图；`updates` chunk 的键即节点名，目前只 `log.debug`，是节点级轨迹的天然接入点；`__interrupt__` 也在同一流里。
- run 结束处已调用 `checkpoint_version()` → `graph.aget_state`，可顺带取回完整 state 派生会话事实，不增加额外查询。
- 模型调用统一在 `app/models/router.py` 两处 `record("model_call", …)`；检索在 `graph.py:838 record("knowledge_search", …)`；`record()` 已是 JSONL + Langfuse + 告警的公共出口，加一个 sink 分发即可。
- 规则 / 校验类事件（`rule_hit`、`cp_verify`、`a1_complete`、`step_ready`、`step_dropped`、`plan_exhausted`、`synthesize`、`query_rewrite`、`rediagnose`）走 `log.info(..., extra={"event": ...})`，不经 `record()`；用 logging Handler 按 `event` 白名单捕获可零侵入。
- `cards.py` 已用 `langgraph.config.get_config()["metadata"]["langgraph_step"]`；同一 metadata 含 `langgraph_node`，可给 model_call / knowledge_search 打节点名（节点外调用抛错，需 try/except）。langgraph 1.2.11。
- JSONL 实测：3353 行 2.3 MB；事件分布 state_transition 428、session_event 386、model_call 310（含全量 prompt）、run_metric 247、knowledge_search 122。10 MB × 3 轮转 ≈ 几天就丢。
- 本机 haike 库：sessions 601、session_events 11909（506 会话 / 511 run）、checkpoints 1891（173 thread）。checkpoint `metadata` 只有 `{step, source, parents}`，无节点名。
- 契约 `Stage` 8 值、`Feedback` solved/not_solved/cannot_do、升级规则号 R1/R1b/R1c/R2/R3/R4/R5/R7/R8；`close` 节点写 `stage=done` + `visible_messages[kind=closing]` + 结构化 `a1_complete`，是「已解决」的确定信号。
- 数据保留（票 48）：会话 24 h 整体删除（含事件 / checkpoint / 图片），追踪 7 d；`retention.SESSION_TABLES` 列出七张表。管理员历史必须放在独立 TTL 的表里。
- 鉴权现状：仅 `DELETE /sessions/{id}` 用 `X-Admin-Token == ADMIN_TOKEN`；未配置即 403。可直接复用为 admin 依赖。
- 前端：单入口 SPA、无路由库、无图表 / 图库；依赖 react 19 / zod / react-markdown；样式 CSS Modules + tokens.css（含暗色）；契约类型由 `make contracts` 生成。
- Langfuse 4.35.0 本机 profile 已在跑（web / worker / clickhouse / minio / obs-postgres / obs-redis），以 session_id 关联 generation；适合作 prompt 级排查的深链目标，不必自建。
- 已有可复用的迭代工具：`app/replay`（录制包，键不含 session / 时间）、`app/bakeoff`（样本 × 候选 × 四指标 × 门槛）、`app/inspection`（进程内巡检场景 + findings 回填）、`haike-kb ingest`（幂等灌库 + manifest 版本）。

## Phase 1 实施中验证 / 修正的事实（2026-09-13）
- `checkpoint_writes.task_path` 形如 `~__pregel_pull, <node>`，join `checkpoints.metadata->>'step'` 即可还原**历史**会话的节点执行序列；配合各 run 的 `done.version`（= 该 run 最后一个节点的 write_step + 1）可把节点分配到 run。设计时以为历史 DAG 不可重建，实际可以，只是没有耗时。
- 真实校验样本（会话 439795d8）：run1 version=4 → intake/disambiguate/prepare_card/await_input（write_step 0–3）；run2 version=9 → apply_action/retrieve/reply/guide/await_input（4–8）；run3 → apply_action/close。
- **run_id 不是全局唯一**：历史 / 测试数据里 `run-a`、`run-b`、`run-0` 等被 100+ 个会话复用。以 run_id 单独做主键会静默合并行（854 run 只落 514 行）。事实表一律用 (session_id, run_id)。
- 模型 / 检索事实是不可变历史，用自然键（含微秒时间戳）唯一索引 + `on conflict do nothing`，回填才幂等；`nulls not distinct` 覆盖会话外的调用。
- 规则命中不必单建表：R 编号、verify 判定、plan_id 都在节点返回的 state 更新里，`node_runs.summary` 白名单即可捕获，故 Phase 1 未做 logging Handler 接入点（原计划的接入点 ②）。
- 现库 601 会话中只有 173 个还有 checkpoint（24 h TTL 已清理其余），故演示期需把 `RETENTION_SESSION_HOURS` 调到 168。

## 缺口
- 无节点级轨迹、无落库的模型 / 检索 / 规则事实、无结果分类、无 user_ref、无案例 / 标注、无管理端鉴权体系、无长期保留。详见 01_design.md §2.2。

## 参考
- 票 44 可观测（deploy/observability/README.md）、票 48 保留与脱敏（app/retention.py、app/observability/privacy.py）、票 43 回放（app/replay/package.py）、票 45 巡检（app/inspection）、票 42 bake-off（app/bakeoff）。
