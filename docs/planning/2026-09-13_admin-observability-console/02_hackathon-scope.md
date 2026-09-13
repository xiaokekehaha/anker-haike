# 黑客松范围收敛（2026-09-13）

01_design.md 是完整蓝图；本文件是**本次实际做的范围**。原则：演示效果优先、几天内可交付、不做鉴权、不考虑大规模用户，扩展点保留但不实现。

## 1. 取舍表

| 项目 | 完整设计 | 黑客松做法 | 理由 |
| --- | --- | --- | --- |
| 鉴权 | ADMIN_TOKEN 门 + 反代 SSO | **不做**；`/admin/` 直接可访问，README 注明生产需反代 | 用户明确不考虑 |
| 用户标识 | `sessions.user_ref` + 按用户聚合 | **不做**；旅程 = 会话旅程 | 演示场景无真实用户体系 |
| 事实表 | 9 张（含 rule_hits / messages / daily_rollups） | **5 张 + cases**：session_facts、run_facts、node_runs、model_calls、retrieval_calls、cases | 规则命中折进 node_runs.summary 与 outcome_reason；无预聚合，直接 SQL |
| 脱敏文本表 messages | 30 d TTL | **不做**；改为把演示期会话保留时间调到 7 d（`RETENTION_SESSION_HOURS=168`），完整时间线走现有快照接口；session_facts 只存脱敏后的 `first_question` | 少一张表、少一套写路径，演示期数据量小 |
| analytics 独立 TTL / 分区 / BRIN / 只读池 | 有 | **不做**；`make reset` 一起清 | 量小 |
| sink | 有界队列 + 批写 + 溢出计数 + health 字段 + 告警 | 有界队列 + 单 worker 批写 + 溢出只打日志 | 保留“不阻塞主链路”的底线 |
| 采集接入点 | ① record() ② logging Handler ③ runner | **同**（三个都做，改动都很小） | 这是 DAG 与面板的数据来源，不能省 |
| 结果分类 derive | 全表 + abandoned 定时改判 | 全表；abandoned 在查询时按 `last_run_at < now()-6h` 现算 | 省一个后台任务 |
| 回填 CLI | backfill / rollup / purge / export-case | **backfill + export-case** | 现库 601 会话要补进面板做演示 |
| Admin API | 11 个 | **7 个**：sessions 列表、会话旅程、graph、metrics/overview、metrics/flow、cases 列表/标注、cases 导出 | 模型 / 检索健康并入 overview |
| 契约 | Pydantic → JSON Schema → TS codegen | 后端 Pydantic 响应模型；前端手写 TS 类型 | 不动 `make contracts` 流程 |
| 前端 | 5 页 + TokenGate + react-query | **4 页**：Dashboard（含聚合 DAG 卡）、Sessions、Journey、Cases；无 TokenGate；fetch + 自写 hook | Flow 并入 Dashboard 一张卡 |
| DAG | React Flow + dagre，三层 | **同** | 演示核心 |
| 图表 | ECharts 按需 | ECharts 按需（bar / line / pie） | Sankey 不做，聚合 DAG 用 React Flow 边宽表达 |
| 案例闭环 | 标注 + 4 种导出 + CI 门 + 自动候选 + 周复盘模板 | 标注 + **导出 replay 录制包 / kb 候选 Markdown** + 简单自动候选（升级原因 R1/R1b/R1c/R2/R5/R7 或 error → review） | “一键把好会话变演示录制包”“坏会话归因”是最能讲的两个故事 |
| 测试 | 全量 | derive 表驱动单测、sink 不阻塞单测、API 冒烟、GraphView 高亮组件测试 | 保底 |

## 2. 决策默认值（不再等确认）

| # | 决策 | 取值 |
| --- | --- | --- |
| D1 | 脱敏文本 | 只存 `first_question`（sanitize 后 ≤ 200 字）；完整对话靠 7 d 原始会话 |
| D2 | 解决率 | 自助解决率 = resolved / (resolved + escalated[R1,R1b,R1c,R2,R5,R7] + abandoned[guide/verify])；面板同时显示闭环率 |
| D3 | user_ref | 不做 |
| D4 | 鉴权 | 不做 |
| D5 | 面板 | 自建 |
| D6 | 自动候选 | 做最简版，只进 review |

## 3. 演示脚本（倒推需求）

1. 打开 `/admin/`，Dashboard：今日 / 7 日会话数、自助解决率、升级原因分布、品类 / 故障计划分布、首可见 P95、模型降级率；下方一张聚合 DAG（边越粗走的人越多，升级分支一眼可见）。
2. 点进 Sessions，筛 `outcome=escalated, reason=R2`，打开一个会话：左侧 run 列表，中间切「时间线 / 瀑布 / DAG」，DAG 上高亮这次 run 实际走过的节点与耗时，点 `retrieve` 看 no_match、点 `guide` 看模型 attempts。
3. 在该会话上标注 bad + `knowledge_missing`，导出 kb 候选 Markdown；再打开一个 resolved 会话标 good，一键导出 replay 录制包，`make replay-verify` 通过。
4. Cases 页看坏案例按原因分布与状态。

## 4. 分期与估时（合计约 4–5 个工作日）

| 阶段 | 内容 | 估时 |
| --- | --- | --- |
| P1 数据底座 | 迁移 0004（5 表 + cases）、sink、三个接入点、derive、backfill、保留时间改 7 d | 1.5 d |
| P2 Admin API | 7 个接口 + graph 导出 + 冒烟测试 | 0.5 d |
| P3 前端 | 第二入口、Dashboard、Sessions、Journey（时间线复用 / 瀑布 / DAG）、聚合 DAG 卡 | 1.5–2 d |
| P4 案例 | cases API、标注 UI、export-case（replay / kb 候选）、Cases 页 | 0.5–1 d |

## 4.1 Phase 1 实施结论（2026-09-13 完成）

| 计划 | 实际 | 说明 |
| --- | --- | --- |
| 5 事实表 + cases | 同 | 迁移 0004，独立 `analytics` schema |
| 三个采集接入点 | **只做两个**（record() 尾部、runner） | 规则命中已在节点状态更新里，logging Handler 无增量信息，省掉 |
| 回填只补 session_facts / run_facts，节点轨迹补不回来 | **节点轨迹也补回来了** | `checkpoint_writes.task_path` 带节点名，历史 DAG 路径真实可重建（无耗时） |
| — | 新增：事实表主键用 (session_id, run_id) | 历史数据里 run_id 跨会话复用 |
| — | 新增：模型 / 检索行自然键去重 | 回填幂等 |

## 5. 明确后移（写进 01_design.md，不在本轮做）
鉴权与角色、user_ref、messages 脱敏表与独立 TTL、daily_rollups / 分区 / 只读池、health / 告警接入、bakeoff / inspection 导出与 CI 门、Sankey、契约 codegen、周复盘模板。
