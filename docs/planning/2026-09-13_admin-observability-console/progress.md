# 进度

- 2026-09-13：盘点现有数据源与工具链；验证图拓扑导出、runner updates 流、record()/logging 接入点；写成 01_design.md（架构 / 数据模型 / 后端 / 前端 / DAG / 指标口径 / 案例闭环 / 性能）与 task_plan.md 五个阶段。
- 2026-09-13：按黑客松口径收敛（不做鉴权 / 大规模），写 02_hackathon-scope.md，D1–D6 取默认值，task_plan 重排为 4 个阶段约 4–5 天。
- 2026-09-13：**Phase 1 数据底座完成**。迁移 0004（analytics schema，5 事实表 + cases）；sink / store / derive / hooks / trace / backfill / CLI；runner 与 record() 接入；43 项新测试，全量 492 passed，ruff 通过。
  - 意外收获：`checkpoint_writes.task_path` 带节点名，历史会话的 DAG 路径可真实重建（不是估算），回填出 1538 条节点轨迹。
  - 回填实测：509 会话 / 854 run / 1538 节点 / 310 模型调用 / 122 检索；335 个会话因 checkpoint 已按 TTL 清理而无节点轨迹。
  - 两处按真实数据修正：run_id 在历史 / 测试数据里跨会话复用 → run_facts 主键改 (session_id, run_id)、node_runs 唯一键改 (session_id, run_id, idx)；模型 / 检索行加自然键去重索引，回填可反复跑。
  - 按真实分布修正口径：208 个「失败」其实全是开发期重启打断（server_restarted）→ 新增 `interrupted`；checkpoint 已过期的会话 → 新增 `unknown`。两者都不进解决率，避免把开发噪声当产品失败。现库终局分布：resolved 21 / escalated 26 / errored 3 / awaiting_user 43 / in_progress 81 / unknown 337。
  - 线上验证（真实模型 + WeKnora，容器已重建重启）：一条 A1 消息完整落库——节点路径 `intake(2530ms) → disambiguate(15ms) → retrieve(2268ms) → reply(1040ms) → guide(1355ms)`；run 事实 first_visible=5185ms / card_ready=7211ms(step_card) / 5 节点；会话事实 awaiting_user·step_feedback、EUFY-X9-PRO、robot_vacuum、4 次模型调用、4091/480 token；模型与检索行都带正确的节点归属（`langgraph_node` 取用成功）。

- 2026-09-13：**Phase 2 Admin API 完成**。`app/analytics/queries.py`（只读 SQL，参数化，statement_timeout 5s）+ `app/admin/`（router / graph_export）。7 个端点：
  - `GET /admin/api/graph` 静态拓扑（从编译图导出，21 节点 / 46 边，带节点→阶段归类与条件边标记，进程内缓存）
  - `GET /admin/api/sessions` 列表：时间窗 / 结局 / 原因 / 品类 / SKU / 计划 / 关键词筛选 + keyset 分页
  - `GET /admin/api/sessions/{id}/journey` 旅程：会话事实 + 每个 run 的节点轨迹 / 模型 / 检索 + 案例标注 + 原始快照（未过期时）
  - `GET /admin/api/metrics/overview` KPI / 趋势 / 维度分布 / 模型健康 / 检索健康
  - `GET /admin/api/metrics/flow` 聚合 DAG 的边计数、节点中位耗时与中断数、入口分布
  - `GET|POST|PATCH /admin/api/cases` 案例标注与状态流转（一会话一条，重复标注即更新；原因标签服务端校验）
  - 两个查询期口径：`abandoned` 按 last_run_at 现算（改阈值不用重算库）；解决率分母排除 unknown / interrupted 与政策类升级（R3/R4/R8）。
  - 分母为 0 时 rates 返回 null 而不是 0——「没有数据」不能显示成 0%。
  - `cases/{id}/export` 未做：导出器属 Phase 4，不先放空壳端点。
  - 线上验证（容器已重建重启，打真实数据）：
    - overview：513 会话 / 解决 21 / 升级 26（系统 9、政策 16）/ 放弃 103 / unknown 337；首可见 P95 5133 ms、首卡 P95 6509 ms；模型按 task 分组（guide.step 89 次 P95 1872 ms 等）；检索 kb_tickets 有 4 次 no_match。
    - journey：真实会话完整呈现——路径 `intake(2530ms) → disambiguate(15ms) → retrieve(2268ms) → reply(1040ms) → guide(1355ms)`，每个节点挂着对应的模型调用与检索，并附带原始快照（5 条时间线）。
    - flow：top 边 intake→disambiguate 165 次、retrieve→reply 163 次；入口分布 intake 195 / apply_action 179 / rediagnose 20；最慢节点 intake 2530 ms、retrieve 2268 ms。
  - **注意**：当前库里的比率不能当产品指标引用——103 个「放弃」绝大多数是开发期没有续跑的测试会话，把自助解决率压到 15.79%。演示前建议用干净数据或按时间窗过滤。
  - 全量 519 passed、ruff 通过。期间一度看到 `tests/test_retrieve_p0.py` 两条失败，排查为另一会话正在同时改这个文件（断言改到一半），其修正后即恢复；与本次改动无关。

- 2026-09-13：**Phase 3 管理端前端完成**。`frontend/admin/index.html` 第二入口 + `src/admin/`（4 页 + 7 个组件），构建产物 `dist/admin/index.html`，编排服务加 `/admin/{path}` 深链回退，Vite 开发期加同名中间件。
  - 页面：经营面板（KPI + 趋势 + 结局构成 + 维度分布 + 模型/检索表 + 聚合 DAG）、会话列表（筛选/搜索/翻页）、会话旅程（左 run 列表 | 对话 / 节点瀑布 / 流程图 三视图 | 右节点详情）、案例复盘（标注 + 原因分布 + 状态流转）。
  - 线上验证（真实数据）：旅程页还原出 `理解诉求 2.5s → 产品消歧 15ms → 检索知识 2.3s → 生成回复 1.0s → 下发步骤 1.4s`，每个节点挂着模型调用与检索明细；流程图高亮实走路径；对话页渲染完整快照；标注保存后案例页出现「好案例 · 值得沉淀」。
  - 依赖取舍：只装 @xyflow/react 与 react-router-dom。**dagre 没装**——节点按「阶段」分列更贴合领域，40 行布局即可；**echarts 没装**——面板只需要折线、横条、堆叠条三种形式，手写 SVG 约 150 行，省掉近 1 MB 依赖。客户端聊天包已核验未混入图库（`grep xyflow dist/assets/index-*.js` 为 0）。
  - 不复用聊天端 Timeline：它绑定会话状态与交互，且另一会话正在改；管理端另写了只读渲染器，两边互不影响。
  - 配色按 dataviz 技能执行：趋势两系列用分类槽 1/2（`#2a78d6`/`#eb6834`，浅深两模式全部检查通过）；结局用保留状态色，堆叠顺序定为 good → warning → critical → serious，因为校验器指出 warning 与 serious 相邻时常视觉 ΔE 13.6 低于 15 的底线，换序后 15.7 通过；每段都带文字标签，颜色从不单独表意；分母为 0 时显示「—」而不是 0%。
  - 修掉两个自查发现的问题：横条 track 是 `<span>`（inline 元素 height 不生效）导致条形整体不可见；React Flow 的 `hideAttribution` 需要 Pro 订阅，已去掉并保留署名。
  - **浏览器实测抓到一个真 bug**：时间窗在渲染里直接算 `Date.now()`，每次渲染都得到新的 `from` → useAsync 依赖变化 → 无限重取，实测对后端打出 500 次请求。改为按 `days` 记忆，并补了页面级回归测试（断言一个时间窗只取一次数）。这条只有「真的把页面跑起来看」才会暴露。
  - Dockerfile 只 COPY 了 `frontend/index.html`，漏掉 `frontend/admin/`，镜像里静默少打一个入口、线上 `/admin` 404。已补 COPY，并在 vite.config 加入口存在性断言：缺文件就让构建失败，不再静默。
  - 部署验证：容器重建重启后 `/admin/`、`/admin/sessions`、`/admin/cases`、`/admin/sessions/<id>` 全部 200，`/admin/api/*` 与客户端 `/` 不受影响；面板在真实数据上显示 514 会话、自助解决率 15.0%、闭环率 44.7%、首可见 P95 4.9 s。
