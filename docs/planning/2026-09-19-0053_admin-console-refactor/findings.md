# 观测台现状审计

日期：2026-09-19。范围：`frontend/src/admin/**`（约 1.9k 行）、`orchestrator/app/admin/**`（约 570 行）、`orchestrator/app/analytics/**`（约 2k 行）。方法：通读全部前端页面与组件、两个后端路由、analytics schema / derive / queries；用本会话 dev 服务器（5174，代理到本机 8000 真实库）在 1360 px 走查五个页面；抓真实接口数字。对照 [01_design.md](../2026-09-13_admin-observability-console/01_design.md)（完整蓝图）与 [02_hackathon-scope.md](../2026-09-13_admin-observability-console/02_hackathon-scope.md)（实际范围）。

## 1. 现状结构

```
/admin  (BrowserRouter basename=/admin)                      后端
├ /            Dashboard   9 张 KPI + 趋势 + 结局构成 + 分布 + 模型/检索表 + 聚合 DAG    /metrics/overview  /metrics/l3  /metrics/flow  /graph
├ /sessions    Sessions    搜索 + 结局 + 时间窗 + 游标翻页                                /sessions
├ /sessions/:id Journey    左 run 列表 | 对话 / 节点瀑布 / 流程图 | 右节点详情 + 标注     /sessions/{id}/journey
├ /approvals   Approvals   L3 案件队列（状态 / 优先级）                                    /cases/queue          (l3_router)
├ /approvals/:id CaseDetail 会话记录 | 方案与判定 | 人工决定 / 结案 / 重开                /cases/{id} /decision /close /reopen
└ /cases       Cases       复盘标注库（好 / 坏 / 待复盘 + 原因标签 + 状态）               /cases (analytics)     (router)
```

两套 API 客户端（`api.ts` 与 `l3.ts`）、两套类型（`types.ts` 手写 + `l3.ts` 内联 + 从生成的 `types/events.ts` 借 `PolicyDecision` 等）、两种样式写法（Dashboard / Sessions / Journey / Cases 用 `admin.css` 的 `.card .filters .btn`；Approvals / CaseDetail 几乎不用类，裸 `<table>` `<button>`）。

提交历史：观测台在 `4bba1b9` 一次落地（2026-09-13），之后 L3 审批页随 `5d0f609` / `7737fb2` 等 L3 提交叠加进来，没有再做过整体整理。

## 2. 问题清单（带证据）

### 2.1 结构与定位

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| S1 | **三种使用者混在一个导航里**：运营（KPI）、人工审核坐席（队列 / 决定）、研发（瀑布 / DAG / 节点判定字段 / 上下文预算 / 标注）。四个导航项按「对象」而不是按「谁来用」组织，坐席进来第一屏是 9 张研发口径 KPI 与一张 DAG | [App.tsx](../../../frontend/src/admin/App.tsx) 导航；[Dashboard.tsx](../../../frontend/src/admin/pages/Dashboard.tsx) |
| S2 | **两个「案件」**：L3 服务案件（`cases` 表，状态 awaiting_approval / executing / closed…）与复盘标注（`analytics.cases`，verdict good / bad / review）在导航里分别叫「售后审批」「案例复盘」，代码里都叫 case，`CaseRow` 与 `ServiceCase` 并存 | [types.ts](../../../frontend/src/admin/types.ts) `CaseRow`；[l3.ts](../../../frontend/src/admin/l3.ts) `ServiceCase` |
| S3 | **L3 页面是后来焊上去的**：Approvals / CaseDetail 不用 `.card` 与统一筛选栏，不走 `useAsync` 之外的任何共享组件，`l3-case-grid` 三栏在 1100 px 以下直接堆成一列 | 截图：Approvals 页裸表格；[admin.css](../../../frontend/src/admin/admin.css) 末尾 `.l3-case-grid` |
| S4 | **只读对话渲染重复实现**：`ReadonlyTimeline` 自写 12 种卡片的降级渲染，`types.ts` 手写 `TimelineItem` 子集与生成契约漂移（如 `assistant_message` 缺 `at`、`step_card` 缺 `observations` / `observation_answers`、`escalation_summary` 只有 3 个字段） | [ReadonlyTimeline.tsx](../../../frontend/src/admin/components/ReadonlyTimeline.tsx)；[types.ts:77](../../../frontend/src/admin/types.ts:77)。当时的理由是「聊天端在改，解耦」；聊天端现已有 `reducer(restore)` 与 `deriveRecord`，可以零成本复用 |
| S5 | **契约手写**：02 范围决定管理端不进 `make contracts`；L3 又引入 `ServiceCase` / `L3Metrics` 手写类型，后端 `l3_router.detail` 还在运行时往 row 里塞 `commitments` / `executions`，前端类型里没有这两个字段 | [l3_router.py:63](../../../orchestrator/app/admin/l3_router.py:63) |

### 2.2 看板口径

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| K1 | **两套分母并列且互相矛盾**：第一行 KPI 按「问题（episode）」算（托管率 16.2%），第二行按「会话」算（自助解决率 2.4%、闭环率 6.3%）。同一屏出现 16.2% 与 2.4% 两个「解决率」，没有任何文字解释差异 | 真实接口：`/metrics/l3` managed_rate 0.162；`/metrics/overview` self_service 0.024（2026-09-19 近 7 天） |
| K2 | **看板无法剔除测试流量**：`analytics.session_facts` 没有 `source` 列；L3 指标按 `service_episodes.source` 剔除 replay / smoke，overview 不剔除。近 7 天 157 个会话里 92 个「已放弃」，几乎都是开发期会话 | [schema.py:27](../../../orchestrator/app/analytics/schema.py:27) 无 source；[l3.py](../../../orchestrator/app/analytics/l3.py) `source == "live"` 过滤；13 日 progress 已警告「比率不能当产品指标引用」 |
| K3 | 9 张 KPI 里 4 张的口径只在 `title` 悬停里，评审看投影看不到 | [Charts.tsx](../../../frontend/src/admin/components/Charts.tsx) `Kpi` 用 `title={hint}` |
| K4 | 「全部」= 近 365 天，不是全部 | [Dashboard.tsx:20](../../../frontend/src/admin/pages/Dashboard.tsx:20) |
| K5 | 聚合 DAG 在 1360 px 下 21 个节点挤成一行，节点文字不可读；它回答的是研发问题「流量走哪条边」，放在运营首页底部 | 截图第 2 张 |
| K6 | 五个评审难点（看图 / 问清 / 分流 / 接稳 / 幻觉）没有任何专门指标。数据其实有一部分：`session_facts.emotion_level`、`clarifications`、`knowledge_status`、`node_runs.summary.vision_status`、案件 `gate_result`、摘要 `emotion_track` | [schema.py](../../../orchestrator/app/analytics/schema.py)；[derive.py:41](../../../orchestrator/app/analytics/derive.py:41) `_SUMMARY_KEYS` |

### 2.3 坐席审批

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| A1 | 队列只显示 `case_id` 前 8 位、订单号、状态、等待分钟、政策 id，**没有产品、问题、客户情绪**。后端 `queue()` 是 `select * from cases`，没 join 会话事实 | 截图 Approvals；[store.py:168](../../../orchestrator/app/cases/store.py:168) |
| A2 | 等待时间显示「6060 分钟」，无 SLA 分级与颜色；队列默认状态 awaiting_approval，但 `status=` 空时把 tracking / open 也列进「审批」 | 截图；真实队列 18 条里 status 混有 tracking / open |
| A3 | 详情页决定表单**写死换货**：下拉文案「批准换货」，提交按钮 `remedy !== 'replace'` 即禁用；与 service-flow-realignment D-SR-4（增加 parts / paid_repair）冲突 | [CaseDetail.tsx](../../../frontend/src/admin/pages/CaseDetail.tsx) `selectedOption?.remedy !== 'replace'` |
| A4 | 判定依据以 `JSON.stringify(expected / actual)` 原样打印；政策 id `cn_robot_vacuum_standard` 直接给坐席看；「授权检查」只有 ✓ / × 加 detail | 同上 |
| A5 | 详情页复用了聊天端的 `ProposalCard`（交互组件置空回调），却没有复用会话记录，改用自写 `ReadonlyTimeline`；两个方向不一致 | 同上 |
| A6 | 案件详情与会话旅程互不链接：CaseDetail 拿到 `session_id` 但没有到 `/sessions/:id` 的入口；Journey 不知道该会话有没有案件 | 两页代码均无对方路由 |
| A7 | 保存决定后的反馈只有一行 `role=status` 文本；`resume` 按钮文案「重新投递已保存的决定」对坐席不可理解 | 同上 |

### 2.4 会话与旅程

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| J1 | 旅程默认打开「节点瀑布」（研发视角），对话在第一个 tab 却不是默认 | [Journey.tsx:23](../../../frontend/src/admin/pages/Journey.tsx:23) `useState<View>('waterfall')` |
| J2 | 节点详情 `dt/dd` 直接打印状态键（`plan_id` 等有中文映射，其余原样） | [NodeDetail.tsx](../../../frontend/src/admin/components/NodeDetail.tsx) |
| J3 | 会话列表只暴露结局 + 关键词 + 时间窗三个筛选，后端支持的 reason / category / sku / plan 没接；没有案件状态列 | [Sessions.tsx](../../../frontend/src/admin/pages/Sessions.tsx)；[router.py:52](../../../orchestrator/app/admin/router.py:52) |
| J4 | 复盘库为空（0 条标注），02 §3 演示脚本里的「一键导出 replay 录制包 / kb 候选」**没有实现**：`export-case` 在 CLI、API、前端都不存在 | `grep export` 于 analytics/cli.py 与 admin 路由为空；截图 Cases 页 |

### 2.5 横切

- 无鉴权（02 §1 决策，README 应注明生产需反代）；`l3_router.actor()` 在非 dev 环境要求 `X-Authenticated-User`，观测台 `router.py` 不要求，两个路由口径不一。
- `admin.css` 全局类名，与聊天端 CSS Modules 不同源；深色下 `.dagnode` 内联 `#fff` / `#0b0b0b` 写死。
- 前端测试 24 条，覆盖图表 / 瀑布 / DAG / 格式化与两页取数回归；Approvals / CaseDetail / Journey / Cases 页无测试。

## 3. 可用数据（决定哪些改动不需要后端）

| 想展示的 | 现有来源 | 结论 |
| --- | --- | --- |
| 客户看到的完整对话 + 服务记录 | `journey.snapshot` / `case.snapshot`（未过期时） | 前端可直接 `reducer(initialState, {type:'restore', snapshot})` 得到 `SessionState`，复用聊天端 `Timeline` + `RecordPanel` |
| 情绪等级 / 策略 | `session_facts.emotion_level`（首轮）；摘要 `emotion` / `emotion_track` | 会话级可得；逐轮只有升级后 |
| 澄清次数 / 排障步骤数 / 知识状态 / 凭证状态 | `session_facts` | 可得 |
| 读图结果 | `node_runs.summary.vision_status`、`step_card.seen` | 可得（节点级） |
| 授权四项检查、政策条款、需人工原因 | `ServiceCase.gate_result` / `policy_decision` | 可得 |
| 案件对应的产品 / 问题 / 情绪 | 需要 `cases` join `analytics.session_facts` 或 `sessions` | **后端**：`queue()` 加 join 或前端二次请求 |
| 剔除 replay / smoke 的会话级指标 | `session_facts` 无 `source` | **后端**：derive 时从 `evaluation_source` 落列 + 回填 |
| 五难点专项指标（读图可用率、澄清超限率、分流准确率、情绪分级分布、引用覆盖率 / 越权） | 部分可从现表聚合（emotion_level、clarifications、knowledge_status、越权 SQL 已有）；分流准确率依赖人工标注 | 一半前端可做，一半要新查询 |
| 导出 replay 录制包 / kb 候选 | 无 | **后端**：新 CLI + API |
