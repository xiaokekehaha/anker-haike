# 管理员观测台（用户旅程 / 经营面板 / DAG / 案例闭环）

## Goal
为管理员提供：按会话（将来按用户）回看历史提问与执行旅程（时间线 + 节点瀑布 + DAG）；经营面板（品类分布、解决率等 KPI、延迟、模型 / 检索健康）；把好案例沉淀为回放 / 样本 / 知识候选，把坏案例归因复盘并接入回归。设计见 [01_design.md](01_design.md)（完整蓝图）与 [02_hackathon-scope.md](02_hackathon-scope.md)（**本轮实际范围**，黑客松口径：不做鉴权、不考虑大规模用户）。

## 设计结论（摘要）
- 现有表不改结构（仅 `sessions.user_ref` 加列），新增 `analytics` schema 事实表，独立 TTL（90 d / 文本 30 d）。
- 采集走旁路 sink（有界队列 + 批写），接入点：`record()` 尾部、logging Handler 白名单、runner `updates` 流与 run 结束。
- 后端 `app/analytics/` + `app/admin/`（`/admin/api/*`，X-Admin-Token）；前端同工程第二入口 `/admin/`，React Flow + dagre 画 DAG，ECharts 画图表。
- 案例闭环复用 replay / bakeoff / inspection / kb ingest，只新增 cases 表、标注 API 与导出器。

## Phases（黑客松范围，详见 02_hackathon-scope.md）

### Phase 1: 数据底座（后端采集）
**Status:** complete
- [x] Alembic 0004：`analytics` schema 5 表（session_facts / run_facts / node_runs / model_calls / retrieval_calls）+ cases；迁移测试覆盖空库建齐与幂等
- [x] `app/analytics/sink.py`：有界队列 + 单 worker 批写；满则丢并打日志；`InMemoryAnalyticsStore` 供单测
- [x] `hooks.py`：① `record()` 尾部分发（model_call / knowledge_search / run_metric）② logging Handler 白名单（rule_hit / cp_verify / a1_complete / step_ready / plan_exhausted / synthesize）③ runner：`updates` → node_runs，run 结束 → run_facts + derive.session_facts
- [x] `derive.py`：outcome / outcome_reason 纯函数 + 表驱动单测；自动候选（R1*/R2/R5/R7 / error → cases.review）
- [x] `cli.py backfill`：从 session_events + checkpoints + JSONL 回填，幂等；对当前库跑通
- [x] 演示期原始会话保留改 7 d（`.env.example` 与 compose 默认 `RETENTION_SESSION_HOURS=168`）

### Phase 2: Admin API（无鉴权）
**Status:** complete
- [x] `app/admin/router.py`：GET sessions（筛选 + 分页）、GET sessions/{id}/journey（事实 + node_runs + 模型 / 检索 + 24 h/7 d 内附快照）、GET graph、GET metrics/overview、GET metrics/flow、GET/POST/PATCH cases、POST cases/{id}/export
- [x] `graph_export.py`：静态拓扑 + node→stage 映射，进程内缓存
- [x] 接口测试（真实 Postgres，前缀隔离数据，用完即删；18 项）

### Phase 3: 管理端前端
**Status:** complete
- [x] Vite 多页入口 `admin.html` → `/admin/`；dev 代理 `/admin/api`
- [x] 依赖：只加 @xyflow/react + react-router-dom；dagre 与 echarts 都没装（见 Decisions）
- [x] Dashboard：KPI 卡 + 趋势 + 升级原因 / 品类 / 计划分布 + 聚合 DAG 卡
- [x] Sessions：筛选 / 搜索 / 分页 / outcome 徽标
- [x] Journey：run 列表 | 时间线（复用 Timeline 只读）/ RunWaterfall / GraphView | NodeDetail；Langfuse 深链
- [x] 组件测试：GraphView 路径高亮、Waterfall 排序

### Phase 4: 案例沉淀与复盘
**Status:** pending
- [ ] 标注 UI（good / bad / review + 原因标签 + 备注）
- [ ] `export-case`：→ replay 录制包（从 analytics + JSONL 重建键，`make replay-verify` 通过）、→ kb 候选 Markdown
- [ ] Cases 页：三栏 + 原因标签统计 + 状态流转

## Decisions
- 黑客松口径：不做鉴权、不做 user_ref、不做 messages 表 / 独立 TTL / rollup / 分区 / 告警；完整对话靠把原始会话保留调到 7 d。
- 同库新 schema 而非独立库；不存 prompt 全文（交给 Langfuse / JSONL）。
- 节点级轨迹来自 runner `updates` 流而非 checkpoint 表。
- D1–D6 默认值见 02_hackathon-scope.md §2。

## Errors Encountered
- （无）

## Completion
- Phase 3 完成（2026-09-13）：`/admin/` 四个页面跑在真实数据上；17 项新组件测试，前端全量 161 passed，typecheck 与构建通过。客户端包未混入图库（已核验）。
- Phase 2 完成（2026-09-13）：7 个接口（graph / sessions / journey / metrics.overview / metrics.flow / cases CRUD）；18 项接口测试，全量 512 passed，ruff 通过。`cases/{id}/export` 归入 Phase 4（导出器在那里实现，不先放空壳）。
- Phase 1 完成（2026-09-13）：43 项新测试 + 全量 492 passed + ruff 通过；对现库回填出 509 会话 / 854 run / 1538 节点轨迹；`make analytics-backfill` / `make analytics-stats` 可用。
- 下一步：Phase 2 Admin API。
