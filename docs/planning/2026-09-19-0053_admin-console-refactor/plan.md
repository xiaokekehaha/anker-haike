# 智能服务观测台：修改与重构方案（2026-09-19）

用户要求：继续规划，看观测台这部分怎么修改或重构。本轮**只出方案，不动代码**。现状证据见 [findings.md](findings.md)。

## 1. 问题

一句话：观测台是 9/13 为「研发看旅程 + 运营看 KPI」设计的，之后 L3 审批页被焊在同一导航下，于是**三种使用者共用一套按对象组织的页面**，坐席拿不到工作所需的上下文，运营看到两个互相矛盾的解决率，研发的 DAG 占着首页。

具体例子（findings §2）：

- 坐席打开「售后审批」，队列只有 `408885b3 · DEMO-X10-001 · 等待人工审核 · 普通 · 6060 分钟 · cn_robot_vacuum_standard`，看不到这是哪台设备、客户说了什么、情绪如何；点进去判定依据是 `JSON.stringify` 的 expected / actual，决定表单写死「批准换货」。
- 运营打开首页，第一行「独立托管率 16.2%」，第二行「自助解决率 2.4%」，两者分母不同（问题 vs 会话）且都没写在屏幕上；157 个会话里 92 个「已放弃」是开发期噪声，看板没有剔除测试流量的手段。
- 研发的只读对话渲染 `ReadonlyTimeline` 与手写 `TimelineItem` 已与生成契约漂移（缺观察题、缺时间戳、摘要只剩 3 个字段），而聊天端现在有 `reducer(restore)` + `Timeline` + `RecordPanel` 可以直接复用。
- 02 演示脚本第 3 步「标 good 一键导出 replay 录制包」在 CLI / API / 前端都不存在，复盘库 0 条。

## 2. 出发点：谁在用观测台

| 角色 | 要回答的问题 | 现在给了什么 | 缺什么 |
| --- | --- | --- | --- |
| 人工审核坐席 | 该批哪个、为什么、批完客户会看到什么 | 队列 + 详情表单 | 客户上下文、方案对比、SLA、与旅程互链 |
| 运营 / 主管（也是评审现场的观众） | 服务办得怎样、五个难点处理得多深 | 9 张 KPI、趋势、分布 | 单一口径、剔除测试流量、五难点专项 |
| 研发 | 这一轮为什么慢 / 为什么升级 / 模型和检索发生了什么；哪些会话值得沉淀或复盘 | 瀑布、DAG、节点详情、标注 | 导出闭环、筛选维度、与案件互链 |

设计原则：

1. **按角色分工作区，按对象共享详情**。导航是角色入口（工作台 / 看板 / 诊断），会话与案件详情是共享页面，从任何入口进来都到同一处。
2. **坐席看到的对话就是客户看到的**。复用聊天端渲染，不再维护第二套只读渲染器。
3. **一屏只有一个分母**。业务口径以「问题（episode）」为主；会话口径只用于体验与性能。
4. **口径写在屏幕上**，不藏在悬停里。

## 3. 目标结构

```
/admin
├ /desk                    坐席工作台（默认首页 · 角色：坐席）
│   ├ 队列：待审批 | 办理中 | 跟踪中 | 已结案     每行：产品 · 问题摘要 · 情绪/投诉风险 · 等待时长(SLA 色) · 政策结论
│   └ /desk/:caseId        案件详情（共享）：左 客户对话(聊天端 Timeline 只读) | 中 服务记录(RecordPanel) + 方案与判定 | 右 决定
├ /board                   运营看板（角色：运营 / 评审）
│   ├ 顶部：时间窗 · 流量来源(live/replay/smoke) · 品类
│   ├ 业务（按问题）：独立托管率 · NSS · 意图准确率 · 越权执行      —— 一个分母，口径写在卡片上
│   ├ 五难点：看图可用率 · 澄清均值/超限率 · 分流(意图分布+needs_human 原因) · 情绪分级分布 · 引用覆盖/越权
│   ├ 体验与性能（按会话/run）：首可见 P95 · 首卡 P95 · 模型降级率 · 检索 no_match 率
│   └ 分布与趋势（现有）
├ /sessions                会话列表（共享）：筛选补齐 reason/category/sku/plan · 加「案件状态」列
├ /sessions/:id            会话旅程（共享）：默认 tab = 对话(复用聊天端) | 五难点证据 | 节点瀑布 | 流程图 ；右栏 = 服务记录 或 节点详情
├ /lab                     研发诊断（角色：研发）
│   ├ 聚合流程图（从看板搬来）+ 模型/检索健康表
│   └ 复盘库：标注列表 · 原因分布 · 导出 replay 录制包 / kb 候选 · 状态流转
└ 客户端 ↗
```

命名：L3 服务案件统一叫「案件」；`analytics.cases` 在 UI 与前端类型里改叫「复盘记录」（`ReviewRow`），数据库表名不动。

## 4. 方案

三个层次，可以独立决策；P0 是无论如何都该做的修缺陷。

### 方案 P0 修缺陷与统一（不改信息架构，约 1.5 人日）

| 项 | 改动 | 对应问题 |
| --- | --- | --- |
| Approvals / CaseDetail 套 `.card` / `.filters` / `.btn` / `table.data` | 样式统一 | S3 |
| 队列等待时长按 `< 1h / < 1d / ≥ 1d` 分级并着色；默认只看 awaiting_approval，「全部」时按状态分组 | A2 | 
| 队列行加产品 / 问题摘要 / 情绪：前端按 `session_id` 批量取 `session_facts`（现有 `/sessions?q=` 不够，需后端 `queue()` join，见 P2）；P0 先用 `snapshot` 首条用户消息兜底 | A1 |
| 决定表单按 `options[].remedy` / `auto_allowed` 生成，去掉写死的 replace；条款 / 条件用表格与中文标签渲染 | A3 A4 |
| CaseDetail ↔ Journey 互链；Journey 头部显示案件状态 | A6 |
| Journey 默认 tab 改「对话」 | J1 |
| KPI 口径从 `title` 改为卡片下方一行可见说明；「全部」改「近一年」 | K3 K4 |
| Sessions 补 reason / category / sku / plan 筛选与案件状态列 | J3 |
| README 注明观测台无鉴权、生产需反代 | 横切 |

不改路由、不改后端、不改契约。风险最低，但 K1 / K2 / S1 / S4 不解。

### 方案 P1 按角色重组 + 复用聊天端渲染（约 3 人日，含 P0）

1. **路由重组**为 §3 的 `/desk` `/board` `/sessions` `/lab`；旧路径 `/approvals*` `/cases` 做重定向。
2. **只读对话复用**：新增 `admin/components/SessionView.tsx`：`const state = reducer(initialState, { type: 'restore', snapshot })`，渲染聊天端 `<Timeline state onAction={noop} />` 与 `<RecordPanel state />`；删除 `ReadonlyTimeline` 与 `types.ts` 里手写的 `TimelineItem` / `Snapshot`，改用生成的 `SessionSnapshot`。聊天端 `Timeline` 需要一个 `readOnly` 开关把所有卡片 `disabled`（一行 prop）。
3. **案件详情**三栏改为「客户对话 | 服务记录 + 方案判定 | 决定」；服务记录用 `RecordPanel`，方案判定复用 `ProposalCard`（现状）+ 条款表格。
4. **看板重排**：业务口径一行（按问题）+ 五难点一行 + 体验性能一行；DAG 搬到 `/lab`。五难点先用现有数据能算的部分：情绪分级分布（`emotion_level`）、澄清均值与 R7 占比（`clarifications` / `outcome_reason`）、知识 no_match 率、越权次数（已有）；读图可用率与分流准确率标「待接数据」。
5. **旅程页加「五难点证据」tab**：从 snapshot 与 node summaries 派生——看图（`vision_status`、`step_card.seen`、补拍卡）、问清（观察题与答案、澄清轮次）、分流（意图 / task_queue、needs_human 原因）、接稳（`emotion` / `emotion_track` / 策略）、幻觉（每步 `evidence_ids` 数、`primary_evidence_id`、`gate_result`）。这是评审现场「看见五难点」最直接的载体，也是客户端「评审视图」在 D2 里被推迟后的替代方案。
6. 管理端测试：为 `SessionView`（restore → 渲染）、队列行、看板口径各补一条。

依赖聊天端：`Timeline` 的 `readOnly` prop、`RecordPanel` 已可独立渲染。管理端包会引入聊天端卡片组件（无 xyflow 之外的新依赖，体积可忽略）。

### 方案 P2 数据与契约（约 2–3 人日，后端为主，可分批）

| 项 | 改动 | 对应问题 |
| --- | --- | --- |
| `session_facts.source`（live / replay / smoke）：derive 从 `evaluation_source` 落列；迁移 + backfill；overview / sessions 加 `source` 参数，看板默认 live | K2 |
| `cases.store.queue()` join `analytics.session_facts`（first_question / sku / category / emotion_level）；或新查询 `/admin/api/cases/queue?with=session` | A1 |
| 五难点专项查询：`/metrics/difficulties`（读图可用率来自 `node_runs.summary.vision_status`；分流准确率来自复盘标注 `intent_correct/intent_wrong`；引用覆盖率来自 `step_card.evidence_ids` 非空占比，需 derive 新增计数列） | K6 |
| 导出：`haike-analytics export-case <id> --target replay|kb` + `POST /admin/api/reviews/{id}/export`，前端复盘库加按钮，写回 `exported_to` | J4 |
| 契约：`contracts/haike_contracts/admin.py` 定义 `SessionRow` / `Journey` / `ServiceCase` / `ReviewRow` / 指标响应，`make contracts` 生成 `frontend/src/types/admin.ts`，删除手写 `types.ts` / `l3.ts` 类型 | S5 |
| 两个路由的身份口径统一：都走 `actor()`，dev 允许 demo | 横切 |

## 5. 对比与建议

| | P0 | P1 | P2 |
| --- | --- | --- | --- |
| 解决的问题 | A1–A7 部分、J1 J3 K3 K4 | + S1 S2 S3 S4 K1 K5 K6(半) J1 | + K2 K6 A1 J4 S5 |
| 改动面 | 前端 6 个文件 | 前端重组 + 聊天端 1 个 prop | 迁移 1 个、derive / queries / store / 新 CLI / 契约 |
| 评审演示价值 | 低 | 高：坐席工作台 + 五难点证据 tab | 中：数字可信（剔除测试流量）、导出闭环可讲 |
| 风险 | 无 | 复用聊天端组件把两端耦合回来；用 `readOnly` 边界控制 | 迁移与回填；契约化牵动 CI |

**建议：P0 + P1 一起做，P2 里先做 `source` 列与 `queue()` join（各半天），导出与契约化按时间再定。**
理由：P1 的核心是「坐席看到客户看到的」与「五难点可见」，前者靠复用零成本，后者是评审口径直接对应；P2 的 `source` 是让看板数字能拿出去讲的前提，工作量小。契约化收益长期但不影响演示。

## 6. 需要用户决策

| 编号 | 决策 | 建议 |
| --- | --- | --- |
| E1 | 采纳 P0 / P0+P1 / P0+P1+P2 | P0 + P1 + P2 的前两项 |
| E2 | 观测台默认首页：坐席工作台还是运营看板 | 工作台（演示时从「有一个待审批案件」切入更有故事） |
| E3 | 复用聊天端 `Timeline` / `RecordPanel`（两端重新耦合）还是保留独立只读渲染器 | 复用，加 `readOnly` prop |
| E4 | 业务主口径：按问题（episode）还是按会话 | 按问题；会话口径只留体验与性能 |
| E5 | 五难点指标是否进本轮（数据一半缺） | 进：能算的先上，缺的标「待接数据」而不是不放 |
| E6 | `analytics.cases` 改名为复盘（UI + 前端类型），表名不动 | 采纳 |
| E7 | 契约化（`haike_contracts/admin.py`）是否本轮做 | 推后，单独一票 |
| E8 | 决定表单按 remedy 枚举生成后，是否同时放开 parts / paid_repair（依赖 D-SR-4 后端） | 前端按枚举渲染，后端未放开的 remedy 显示为不可批准 |

## 7. 落地拆解（选定后开票）

1. P0：样式统一 → 队列行与 SLA → 决定表单枚举化 → 互链 → 默认 tab → KPI 口径可见 → 会话筛选。
2. P1：`Timeline.readOnly` → `SessionView` → 删 `ReadonlyTimeline` → 路由重组与重定向 → 看板三行 → 五难点 tab → 测试。
3. P2-a：`source` 列 + backfill + 看板过滤；P2-b：`queue()` join；P2-c：导出；P2-d：契约化。

验证：`npm --prefix frontend run typecheck`、`src/admin/__tests__`；后端 `make lint` 与 `tests/test_admin*.py` / `tests/test_analytics*.py`；5174 走查五个页面 1360 / 1024 px；`scripts/ci-local.sh`。

## 8. 不做

- 鉴权与角色体系（02 §5 明确后移，生产靠反代）。
- 用户级旅程 `user_ref`。
- 图表库替换、Sankey。
- 实时旁观正在进行的会话。
