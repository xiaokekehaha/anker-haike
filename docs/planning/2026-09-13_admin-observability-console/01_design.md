# 管理员观测台：用户旅程 / 经营面板 / DAG / 案例沉淀与复盘 —— 架构设计

日期：2026-09-13。来源：orchestrator/app/**、frontend/src/**、contracts/、migrations/、logs/events.jsonl 实测、本机 haike 库实测。
配套：[task_plan.md](task_plan.md)（分期与票）、[findings.md](findings.md)（核对过的事实与缺口）、**[02_hackathon-scope.md](02_hackathon-scope.md)（本轮实际范围：黑客松口径，鉴权 / 规模化 / user_ref 等后移）**。本文件保留完整蓝图作为后续迭代依据。

## 0. 一句话结论

- **现有库表不够，但不用改现有表**：会话骨架（sessions / session_events / checkpoints）只服务在线对话与 24 h 恢复，缺节点级轨迹、模型 / 检索事实、结果分类、用户标识与长期保留。方案是**加一套独立的 analytics 事实表（同库、新 schema、独立 TTL）**，由一个异步 sink 从现有埋点处旁路写入，主链路零阻塞。
- **放置位置**：后端新增 `orchestrator/app/analytics/`（采集 + 查询）与 `orchestrator/app/admin/`（受 X-Admin-Token 保护的 `/admin/api/*`）；前端在同一 Vite 工程里加**第二个入口 `admin.html`**（`/admin/`），与客户端聊天包完全分开打包。
- **DAG**：拓扑直接来自 `graph.get_graph().to_json()`（已验证 21 节点 / 46 边），单次 run 的实际路径来自运行器 `updates` 流的节点更新顺序，聚合流量来自 node_runs 表的边计数。前端用 React Flow + dagre 布局。
- **沉淀与复盘闭环**：在观测台上做「标注 → 案例库 → 金标集 → 回放 / bake-off / 巡检回归 → 知识 / 计划 / 提示词迭代」，全部复用仓库已有的 replay、bakeoff、inspection、kb ingest 工具，只补「案例表 + 标注 API + 导出成录制包 / 样本」这一段。

## 1. 需求与范围

| # | 需求 | 本期交付 | 明确不做 |
| --- | --- | --- | --- |
| R1 | 管理员看某个用户的历史提问、pipeline、DAG，快速看用户旅程 | 会话列表（筛选 / 搜索）→ 会话详情：只读时间线 + 每次 run 的节点瀑布 + DAG 路径高亮 + 模型 / 检索 / 规则明细 + Langfuse 深链 | 实时旁观正在进行的会话（可后续用现有 SSE 续接接口做） |
| R2 | 经营面板：类别分布、关键指标（如解决率） | 概览 KPI + 时间序列 + 按品类 / SKU / 故障计划 / 升级原因分组 + 延迟 P50/P95 + 模型 / 检索健康 + 成本 | 自定义报表编辑器（如需给业务自助分析，接 Metabase / Grafana 读 analytics schema 即可） |
| R3 | DAG 方式展示 | 静态拓扑图；单 run 路径；单会话多 run 叠加；全局聚合流量图（边宽 = 次数） | 在线编辑图 |
| R4（补充） | 好的解决方案沉淀；不好的回答复盘与服务迭代 | 案例标注（好 / 坏 / 待复盘 + 原因标签）→ 案例库 → 导出为回放录制包 / bake-off 样本 / 巡检场景 / 知识候选；复盘看板（坏案例按原因归类、趋势、是否已修复回归） | 自动改写知识库或提示词（保持人工审核门） |

用户标识：当前会话匿名，没有「用户」概念。本期把「用户旅程」落到**会话旅程**，同时在 sessions 上预留 `user_ref`（可空、外部脱敏标识），前端 / 网关能给时就按用户聚合，给不了也不影响其它功能。

## 2. 现状与缺口

### 2.1 已有的数据源

| 数据源 | 内容 | 保留 | 可查性 | 对本需求的价值 |
| --- | --- | --- | --- | --- |
| `session_events`（PG，jsonb） | 15 种契约事件（progress / message / 卡片 / evidence / error / done），按 seq | 24 h（票 48 TTL 整会话删除） | 按 session_id 好查；跨会话统计要扫 jsonb | 24 h 内的完整时间线重放（`GET /sessions/{id}` 快照已能给） |
| LangGraph `checkpoints*` | 权威业务状态（product_state、plans_ranked、steps_executed、escalate_reason、counters…） | 24 h | 只能按 thread 读；metadata 只有 step / source | run 结束时读一次即可派生「结果分类」 |
| `logs/events.jsonl` | `model_call`（含全量 prompt / 输出、attempts、usage）、`knowledge_search`、`state_transition`（stage 级）、`run_metric`、`session_event`；另有 `rule_hit`/`cp_verify`/`a1_complete`/`step_ready`/`synthesize`/`query_rewrite` 等结构化日志 | 10 MB × 3 轮转（实测 3353 行 = 2.3 MB，约 1500 行 / 天就轮没了） | 文件，不能按条件查 | 事实齐全但**留不住、查不动**，是最需要「落库」的部分 |
| Langfuse（可选 profile，本机已起） | 每次模型调用一条 generation，按 session_id 关联，含 io / usage / cost | 自管 | UI + API | 模型调用的 prompt 级排查，不要再自建 |
| `sessions` 投影 | stage / version / active_run | 24 h | 好查 | 只能算「当前在哪」 |

### 2.2 缺口清单

| 缺口 | 影响 | 处理 |
| --- | --- | --- |
| 没有**节点级**轨迹（progress 只到 stage，8 个 stage 对 20 个节点） | 画不出真正的 DAG 路径与节点耗时 | 运行器 `updates` 流按节点写 `node_runs` |
| 模型 / 检索 / 规则事实只在 JSONL | 面板算不了成功率、降级率、token、no_match 率 | sink 落 `model_calls` / `retrieval_calls` / `rule_hits` |
| 没有**结果分类**字段（解决 / 升级 / 澄清中 / 放弃…） | 解决率无从定义 | run 结束时由 checkpoint 状态派生 `session_facts.outcome` |
| 24 h 整会话删除 | 管理员看不到历史 | analytics 表独立 TTL（默认 90 d，脱敏文本 30 d） |
| 无 user_ref | 无法按用户串旅程 | sessions 加可空列 + 建会话时可带 |
| 无案例 / 标注 / 金标概念 | 好坏案例无处沉淀 | `cases` + `case_labels` 表与导出器 |
| 无管理端鉴权体系 | 只有 DELETE 用的 ADMIN_TOKEN | 复用 ADMIN_TOKEN 作 API 门；生产由票 46 反向代理再加一层 |

## 3. 总体架构

```
 浏览器
 ┌──────────────────────────────┐    ┌──────────────────────────────────────────────┐
 │ 客户端 SPA  /  (index.html)   │    │ 管理端 SPA  /admin/  (admin.html，独立打包)     │
 │ 现有聊天，不引入图表 / 图库     │    │ Dashboard · Sessions · Journey(DAG) · Flow ·  │
 └──────────────┬───────────────┘    │ Cases(案例库 / 复盘)                          │
                │ SSE / JSON          └───────────────┬──────────────────────────────┘
                ▼                                     │ JSON + X-Admin-Token
 ┌────────────────────────────────────────────────────▼──────────────────────────────┐
 │ orchestrator :8000                                                                │
 │  /sessions  /models  /health            /admin/api/*  (app/admin/router.py)      │
 │       │                                        │  sessions · journey · graph ·    │
 │       ▼                                        │  metrics · flow · cases · labels │
 │  RunManager → runner.RunEmitter ──┐             │                                  │
 │       │  updates 流(节点名/耗时) ──┤             ▼                                  │
 │  StateGraph 节点                  │   app/analytics/queries.py（只读 SQL，参数化） │
 │   ├ ModelRouter.record(model_call)│                                               │
 │   ├ KnowledgeAdapter(knowledge_search)                                            │
 │   └ 规则/verify 结构化日志(rule_hit…)                                              │
 │                                   ▼                                               │
 │            app/analytics/sink.py  AnalyticsSink                                   │
 │            有界队列 → 批量写（≤200 行 / 1 s）→ 溢出丢弃计数（同 LangfuseExporter）  │
 │            接入点：① observability.record() 尾部  ② logging Handler 按 event 白名单  │
 │                    ③ runner：节点更新 / run 结束（含一次 aget_state 派生会话事实）   │
 └───────────────────────────────────┬───────────────────────────────────────────────┘
                                     ▼
 PostgreSQL（同实例同库 haike）
 ┌ public（现有，24 h TTL）───────────┐   ┌ analytics（新 schema，90 d / 30 d TTL）──────────────┐
 │ sessions(+user_ref) session_events │   │ session_facts  run_facts  node_runs  model_calls     │
 │ session_actions  checkpoints*      │   │ retrieval_calls  rule_hits  messages(脱敏)           │
 │ products plans …                   │   │ cases  case_labels  daily_rollups                   │
 └────────────────────────────────────┘   └──────────────────────────────────────────────────────┘
        ▲ 24 h 内详情 = 现有快照                     ▲ 长期旅程 / 面板 / DAG / 案例
 侧路：haike-analytics backfill（从 session_events + checkpoints + JSONL 回填）
       haike-analytics export-case（案例 → replay 录制包 / bakeoff 样本 / inspection 场景）
       Langfuse（模型 prompt 级排查，管理端按 session_id 深链）
```

设计原则：

1. **旁路写、不进业务预算**。所有采集经有界队列异步批量写；写失败 / 队列满只计数，不影响 run。与票 44 Langfuse 导出器同一套纪律。
2. **不改现有表结构、不改事件契约**。只加 `sessions.user_ref` 一列（可空）。管理端读现有快照接口拿 24 h 内的完整时间线。
3. **事实表存脱敏后的结构化字段，不存 prompt 全文**。prompt 级排查去 Langfuse / JSONL；管理端只存 `privacy.sanitize` 后的用户问句与助手最终文本（可关）。
4. **同库不同 schema**。省一套运维；将来量大再把 `analytics` schema 迁到独立库或 ClickHouse，查询层只改连接串。

## 4. 数据模型（Alembic 0004，schema `analytics`）

所有表带 `created_at timestamptz`；跨会话查询走 `(created_at)` btree（>1 千万行后改 BRIN + 按月分区）；单会话查询走 `(session_id)`。

```sql
create schema if not exists analytics;

-- 会话事实：一会话一行，run 结束时 upsert（权威来源：checkpoint 状态 + 事件）
create table analytics.session_facts (
  session_id        text primary key,
  user_ref          text,                         -- 外部脱敏用户标识，可空
  lane              text,                         -- domestic / overseas
  created_at        timestamptz not null,
  last_run_at       timestamptz not null,
  runs              int  not null default 0,
  user_messages     int  not null default 0,
  first_question    text,                         -- sanitize 后、≤200 字，可由配置关闭
  product_state     text,                         -- confirmed_sku / category_only / unknown
  sku               text, category text,
  emotion_level     text,                         -- calm / anxious / angry（首轮）
  fault_plan_ids    text[] not null default '{}', -- 命中过的排障计划
  steps_executed    int  not null default 0,
  clarifications    int  not null default 0,
  knowledge_status  text,                         -- 最近一次 ok / no_match / unavailable / replay
  receipt_status    text,
  outcome           text not null,                -- 见 §8 口径：resolved / escalated / clarifying / awaiting_user / abandoned / errored / in_progress
  outcome_reason    text,                         -- 升级时的规则号 R1/R1b/R1c/R2/R3/R4/R5/R7/R8；解决时 solved / plan_done
  outcome_at        timestamptz,
  total_latency_ms  int, model_calls int, tokens_in int, tokens_out int,
  raw_available_until timestamptz                -- 原始会话（快照）可用截止 = sessions.updated_at + 24 h
);
create index on analytics.session_facts (created_at desc);
create index on analytics.session_facts (outcome, created_at desc);
create index on analytics.session_facts (category, sku);
create index on analytics.session_facts (user_ref) where user_ref is not null;

-- run 事实：一 run 一行
create table analytics.run_facts (
  run_id text primary key, session_id text not null, seq_no int not null,
  started_at timestamptz not null, ended_at timestamptz, duration_ms int,
  entry text,                -- message / action:select_product / action:step_feedback / ...
  stage_from text, stage_to text,
  done_reason text,          -- completed / awaiting_input / error / cancelled
  error_code text,
  first_visible_ms int, card_ready_ms int, card_kind text,
  model_calls int default 0, tokens_in int default 0, tokens_out int default 0,
  node_count int default 0
);
create index on analytics.run_facts (session_id, seq_no);
create index on analytics.run_facts (started_at desc);

-- 节点执行：DAG 的原材料
create table analytics.node_runs (
  id bigint generated always as identity primary key,
  session_id text not null, run_id text not null, idx int not null,   -- run 内顺序
  node text not null, prev_node text, next_node text,
  started_at timestamptz not null, duration_ms int,
  status text not null,      -- ok / interrupt / error
  summary jsonb              -- 白名单小字段：decision.outcome、knowledge_status、diagnose_outcome、plan_id、verify.outcome、rule
);
create index on analytics.node_runs (session_id, run_id, idx);
create index on analytics.node_runs (node, started_at desc);
create index on analytics.node_runs (prev_node, node);        -- 聚合流量图

-- 模型调用（不存 prompt 正文）
create table analytics.model_calls (
  id bigint generated always as identity primary key,
  session_id text, run_id text, node text, task text not null,
  model_used text, lane text, status text not null,             -- ok / error
  attempts int, fallback_used boolean, stream boolean,
  latency_ms int, tokens_in int, tokens_out int, error_type text,
  created_at timestamptz not null
);
create index on analytics.model_calls (created_at desc);
create index on analytics.model_calls (task, model_used, created_at desc);
create index on analytics.model_calls (session_id, run_id);

-- 检索
create table analytics.retrieval_calls (
  id bigint generated always as identity primary key,
  session_id text, run_id text, node text, round int, kb text,
  product_state text, sku text, category text,
  status text not null,                                          -- ok / no_match / unavailable / replay
  allowed_count int, hits int, top_score real, latency_ms int, rewrite_used boolean,
  query text,                                                     -- sanitize 后，可关
  created_at timestamptz not null
);
create index on analytics.retrieval_calls (created_at desc);
create index on analytics.retrieval_calls (session_id, run_id);

-- 规则命中（CP-in / CP-pre-step / CP-verify）
create table analytics.rule_hits (
  id bigint generated always as identity primary key,
  session_id text, run_id text, checkpoint text not null, rule_id text not null,
  outcome text, created_at timestamptz not null
);
create index on analytics.rule_hits (rule_id, created_at desc);

-- 脱敏对话文本（原会话 24 h 删除后仍可「轻量回放」；独立 TTL 30 d，可整表关闭）
create table analytics.messages (
  id bigint generated always as identity primary key,
  session_id text not null, run_id text, role text not null,     -- user / assistant / card
  kind text,                                                      -- reassurance / reply / closing / step_card / product_card / ...
  text text not null, meta jsonb, created_at timestamptz not null
);
create index on analytics.messages (session_id, id);

-- 案例库与标注（§9）
create table analytics.cases (
  case_id text primary key, session_id text not null, run_id text,
  verdict text not null,          -- good / bad / review
  reason_tags text[] not null default '{}',   -- 见 §9.2 标签集
  note text, labeled_by text, labeled_at timestamptz not null,
  status text not null default 'open',        -- open / exported / fixed / wontfix
  exported_to jsonb,              -- {replay_case_id, bakeoff_sample_id, inspection_scenario, kb_candidate_path}
  fixed_in text                   -- release id / commit
);
create index on analytics.cases (verdict, status, labeled_at desc);

-- 日汇总（面板加速；每 5 min 增量刷新 + 每日重算前一天）
create table analytics.daily_rollups (
  day date not null, dim_kind text not null, dim_value text not null,   -- all / category / sku / plan / rule / model_task / lane
  sessions int, resolved int, escalated int, clarifying int, abandoned int, errored int,
  p50_first_visible_ms int, p95_first_visible_ms int, p50_card_ready_ms int, p95_card_ready_ms int,
  model_calls int, model_errors int, fallbacks int, tokens_in bigint, tokens_out bigint,
  retrievals int, retrieval_no_match int,
  primary key (day, dim_kind, dim_value)
);
```

**与现有表的关系**：不外键。analytics 行的生命周期比原会话长；`session_facts.raw_available_until` 告诉管理端「点进去还能不能拿到完整快照」。

**现有表要动的只有一处**：`alter table sessions add column if not exists user_ref text;`（0004 一并做）。

**是否满足今后扩展**：

- 新指标 = 加列或加 `summary` 白名单键，不改事件契约。
- 新维度（渠道、地区、坐席）= `session_facts` 加列 + `daily_rollups.dim_kind` 加值。
- 多租户 / 多产品线 = 各表加 `tenant` 列 + 索引前缀，查询层统一注入。
- 量级增长路径见 §10。

## 5. 后端设计

### 5.1 目录

```
orchestrator/app/analytics/
  __init__.py
  schema.py        # 行模型（dataclass / Pydantic），与迁移一一对应
  sink.py          # AnalyticsSink：队列、批写、溢出计数、flush/close
  derive.py        # 从 checkpoint state + 事件派生 session_facts / outcome（纯函数，可单测）
  hooks.py         # 三个接入点的胶水：record() 分发、logging Handler、runner 回调
  queries.py       # 全部只读 SQL（列表 / 详情 / 旅程 / 指标 / 流量），参数化，不拼字符串
  rollup.py        # daily_rollups 增量刷新任务
  retention.py     # analytics 独立 TTL
  cli.py           # haike-analytics backfill | rollup | export-case | purge
orchestrator/app/admin/
  auth.py          # require_admin 依赖：X-Admin-Token == settings.admin_token，未配置 → 403 admin_disabled
  router.py        # /admin/api/*
  graph_export.py  # 静态拓扑：graph.get_graph().to_json() → {nodes, edges(conditional), stage_of_node}
```

### 5.2 三个采集接入点（都不改 graph.py 业务逻辑）

| 接入点 | 拿到什么 | 改动 |
| --- | --- | --- |
| ① `observability.runtime.record()` 尾部加 `sink.observe(event, data)` | `model_call`（task、model_used、attempts、usage、latency、status）、`knowledge_search`、`run_metric`、`state_transition` | 1 行；节点名从 `langgraph.config.get_config()["metadata"]["langgraph_node"]` 读（仓库 cards.py 已用同一 API 读 `langgraph_step`，在节点外调用会抛错，try/except 回退 None） |
| ② `logging.Handler`（挂在 root，过滤 `record.event ∈ 白名单`） | `rule_hit`、`cp_verify`、`a1_complete`、`step_ready`、`step_dropped`、`plan_exhausted`、`synthesize`、`query_rewrite`、`rediagnose` | 0 行业务改动，与 JSONL 同源 |
| ③ `sessions/runner.py` | `updates` 流每个 chunk 的键就是节点名 → `node_runs`（顺序、耗时 = 相邻 updates 时间差、`__interrupt__` 标 interrupt）；run 结束处已有 `checkpoint_version()` 调 `aget_state`，改为取回整个 state 交给 `derive.session_facts()` | 约 30 行；`updates` 分支目前只 `log.debug` |

`updates` chunk 的值是该节点返回的 state 更新，`summary` 只抽白名单键（`product_state`、`knowledge_status`、`diagnose_outcome.kind`、`plan_cursor.plan_id`、`_verify.outcome`、`_decision.outcome`、`escalate_reason`、`vision_status`），不落任何自由文本。

### 5.3 结果分类派生（derive.py）

run 结束时按下表判定，写 `session_facts.outcome / outcome_reason`（纯函数，输入 state.values + done.reason + pending_input）：

| 条件（按序） | outcome | reason |
| --- | --- | --- |
| checkpoint 已按 TTL 清理（状态为空） | **unknown** | no_checkpoint（不进任何率的分子分母） |
| done.reason = error 且 code = server_restarted | **interrupted** | 进程重启打断，成败未知，不算产品失败（票 08 reconcile） |
| done.reason = error | errored | error_code |
| done.reason = cancelled 且无 pending | in_progress | cancelled |
| stage = done 且 visible_messages 有 kind=closing | **resolved** | `_verify.rule`（solved / plan_done） |
| stage = escalate 且 escalation_summary 已写 | **escalated** | `escalate_reason`（R1/R1b/R1c/R2 排障失败；R3 用户要人工；R4 安全；R5 知识不可用；R7 澄清超限；R8 范围外） |
| 最近一轮走了 clarify 结束 | clarifying | clarification.reason |
| pending_input 非空 | awaiting_user | pending.kind |
| 其它 | in_progress | — |

`awaiting_user` / `clarifying` / `in_progress` 超过 `ANALYTICS_ABANDON_AFTER_H`（默认 6 h）无新 run，由 rollup 任务改判 **abandoned**（reason = 当时的 stage）。

### 5.4 Admin API

全部 GET 为只读；写只有标注与案例状态。统一 `require_admin` 依赖；`Cache-Control: no-store`。

| 方法 路径 | 用途 | 关键参数 |
| --- | --- | --- |
| GET `/admin/api/sessions` | 会话列表（keyset 分页） | `from,to,outcome,reason,category,sku,plan,rule,user_ref,q(问句 ILIKE),cursor,limit≤100` |
| GET `/admin/api/sessions/{id}` | 会话事实 + run 列表 + `raw_available`（24 h 内则附现有快照） | — |
| GET `/admin/api/sessions/{id}/journey` | 旅程：每 run 的 node_runs + model_calls + retrieval_calls + rule_hits + 脱敏 messages | — |
| GET `/admin/api/graph` | 静态拓扑（nodes / edges / conditional / node→stage 映射） | 进程内缓存 |
| GET `/admin/api/metrics/overview` | KPI 卡 + 时间序列 | `from,to,bucket=hour|day,dim=category|sku|plan|rule|lane` |
| GET `/admin/api/metrics/flow` | 聚合边计数（DAG 流量 / Sankey） | `from,to,category,sku,outcome` |
| GET `/admin/api/metrics/models` | 按 task × model 的成功率 / 降级率 / P95 / token / 估算成本 | `from,to` |
| GET `/admin/api/metrics/retrieval` | no_match / unavailable 率、按 kb / scope | `from,to` |
| GET `/admin/api/users/{user_ref}/sessions` | 按用户串旅程（有 user_ref 时） | — |
| GET / POST `/admin/api/cases`、PATCH `/admin/api/cases/{id}` | 案例库：列表、标注、改状态 | 见 §9 |
| POST `/admin/api/cases/{id}/export` | 导出为 replay / bakeoff / inspection / kb 候选 | `target` |

响应模型放 `contracts/haike_contracts/admin.py`，沿用 `make contracts` 生成前端类型，保持前后端契约一套流程。

### 5.5 回填与运维 CLI

- `haike-analytics backfill [--since]`：从 `session_events` + `checkpoints`（24 h 内的）与 `logs/events.jsonl*`（model_call / knowledge_search / run_metric）重建事实；幂等（按 run_id / (session_id, run_id, idx) upsert）。当前库 601 会话 / 511 run 一次跑完。
- `haike-analytics rollup [--day]`、`haike-analytics purge`、`haike-analytics export-case <case_id> --target replay|bakeoff|inspection|kb`。
- Makefile：`analytics-backfill`、`analytics-rollup`、`analytics-purge`。
- 设置项：`ANALYTICS_ENABLED`（默认 on）、`ANALYTICS_QUEUE_CAPACITY=2000`、`ANALYTICS_FLUSH_MS=1000`、`ANALYTICS_RETENTION_DAYS=90`、`ANALYTICS_TEXT_RETENTION_DAYS=30`、`ANALYTICS_STORE_TEXT=true`、`ANALYTICS_ABANDON_AFTER_H=6`。
- `/health` 增加 `analytics: {queue_depth, dropped, last_flush_at}`；票 50 告警加一条 `analytics_dropped_rate`。

## 6. 前端设计

### 6.1 放哪、怎么打包

- 同一 `frontend/` 工程，Vite 多页：`index.html`（客户）+ `admin.html`（管理）。`build.rollupOptions.input` 两个入口；FastAPI 现有 `StaticFiles(html=True)` 直接能服务 `/admin/`（dist 下 `admin/index.html`，用 `vite` 的 `root`/输出路径映射）。
- 客户包**不得**引入 React Flow / ECharts；ESLint 或 `vite build` 后 size 检查作为 CI 门槛。
- 开发代理加 `/admin/api`。

### 6.2 页面与组件

```
frontend/src/admin/
  main.tsx                 # 第二入口
  App.tsx                  # 路由（react-router-dom）：/ dashboard, /sessions, /sessions/:id, /flow, /cases
  api/admin.ts             # fetch 封装：注入 X-Admin-Token（sessionStorage），401/403 → 登录门
  auth/TokenGate.tsx       # 输入口令（不落 localStorage）；生产在反代后可隐藏
  pages/
    Dashboard.tsx          # KPI 卡（会话数 / 自助解决率 / 升级率 / 澄清率 / P95 首可见 / 模型错误率 / token）
                           # + 时间序列 + 维度切换（品类 / SKU / 计划 / 规则 / 通道）
    Sessions.tsx           # 列表 + 筛选栏 + 关键词 + 分页；行内 outcome 徽标、耗时、run 数
    SessionJourney.tsx     # 三栏：左 run 列表（点选）→ 中「时间线 | 瀑布 | DAG」切换 → 右节点详情抽屉
    Flow.tsx               # 全局聚合 DAG（边宽 = 次数、节点色 = 平均耗时）+ Sankey 备选
    Cases.tsx              # 案例库：好 / 坏 / 待复盘 三栏；原因标签统计；导出按钮；状态流转
  components/
    KpiCard.tsx  TimeSeries.tsx  Breakdown.tsx  DataTable.tsx  FilterBar.tsx
    RunWaterfall.tsx       # 每个节点一条横条（起止 / 耗时），下挂 model_call / retrieval 子条
    GraphView.tsx          # React Flow：静态拓扑 + 高亮路径 + 边计数模式；节点点击 → 详情
    NodeDetail.tsx         # 该节点的 summary、模型调用（attempts / 降级）、检索（scope / hits）、规则
    ReadonlyTimeline.tsx   # 复用现有 Timeline / 卡片组件，onAction 置空 + 只读样式；24 h 外用 analytics.messages 轻量渲染
    LabelDialog.tsx        # 标注：good/bad/review + 原因标签 + 备注
    LangfuseLink.tsx       # 以 session_id 深链到 Langfuse Observations
```

### 6.3 组件库选型

| 用途 | 选择 | 理由 | 备选 |
| --- | --- | --- | --- |
| 路由 | react-router-dom | 页面会继续加，成本低 | 自写 hash 路由 |
| DAG | `@xyflow/react`（React Flow）+ `@dagrejs/dagre` 自动布局 | 交互（点选 / 高亮 / 缩放）最成熟；21 节点 46 边规模无压力 | Mermaid 静态图（无交互，作导出用）；ECharts graph |
| 图表 | `echarts` 按需引入（bar / line / pie / sankey） | 一库覆盖含 Sankey；中文生态 | Recharts（轻，但没有 Sankey）|
| 数据获取 | `@tanstack/react-query` | 缓存、轮询、重试统一 | 自写 hook |
| 表格 | 原生 table + CSS Modules | 与现有风格一致；后期需要虚拟滚动再上 TanStack Table | — |
| 样式 | 复用 `styles/tokens.css`（含暗色） | 一致 | — |

估算：管理端首包 gz 约 350–450 KB（React Flow + ECharts 按需），可接受；客户端包不变。

## 7. DAG 展示设计

三层数据，一套渲染：

1. **拓扑层**（不变）：`/admin/api/graph` → 21 节点 46 边；用 dagre 从左到右布局，按 stage 给节点分组着色（intake / disambiguate / diagnose / guide / escalate / done），`__start__`/`__end__` 画成端点，条件边虚线。布局结果前端缓存。
2. **路径层**（单 run / 单会话）：`node_runs` 按 idx 连成有序路径；命中的节点与边高亮并标序号与耗时；`interrupt` 节点画暂停标记；多 run 叠加时每条 run 一种色相，重复经过的边加粗并标次数。点节点 → 右侧 NodeDetail。
3. **流量层**（聚合）：`/admin/api/metrics/flow` 返回 `(prev_node, node, count, p50_ms)`；边宽 ∝ count，节点填色 ∝ 平均耗时或错误率；筛选按品类 / 结果 / 时间段。适合回答「用户都卡在哪」「哪条分支升级最多」。

Pipeline 视图（瀑布）与 DAG 互补：瀑布看时间（哪一步慢、模型 attempts 几次、检索几轮），DAG 看路径（走了哪条分支、为什么升级）。

## 8. 指标口径

| 指标 | 定义 | 数据来源 |
| --- | --- | --- |
| 自助解决率（主） | resolved / (resolved + escalated[R1,R1b,R1c,R2,R5,R7] + abandoned[stage∈guide,verify])；unknown / interrupted 不进分子分母 | session_facts |
| 总体闭环率 | (resolved + escalated) / 所有已终结会话 | session_facts |
| 升级率（分原因） | escalated 按 outcome_reason 分组 / 会话数；区分「系统失败」(R1*/R2/R5/R7) 与「政策/用户」(R3/R4/R8) | session_facts |
| 澄清率 / 澄清超限率 | 触发 clarify 的会话占比；R7 占比 | session_facts、rule_hits |
| 范围外率 | R8 | rule_hits |
| 首可见 P50/P95、首卡 P50/P95 | 沿用票 44 口径（run 内首次 message / 首张卡；按 run 去重，缺失不补零） | run_facts |
| 每会话步骤数 / run 数 / 时长 | steps_executed、runs、outcome_at − created_at | session_facts |
| 模型：成功率、降级率、P95、token、估算成本 | 按 task × model_used；`fallback_used` = 最终模型 ≠ 链首 | model_calls（成本单价来自 config/models.yaml 扩展字段） |
| 检索：no_match 率、unavailable 率、改写触发率 | 按 kb × product_state | retrieval_calls |
| 错误率 / 取消率 / 超时率 | done_reason、error_code | run_facts |
| 品类 / SKU / 故障分布 | category、sku、fault_plan_ids（unnest） | session_facts |

## 9. 好案例沉淀与坏案例复盘闭环

### 9.1 闭环

```
 线上会话 ──► 观测台标注（人工）／自动候选（规则）──► analytics.cases
                                                          │
          ┌───────────────────────────────────────────────┼──────────────────────────────┐
          ▼ good                                          ▼ bad / review                  ▼
  沉淀为「资产」                                   复盘归因（原因标签）              金标集（回归）
  · 导出 replay 录制包 → 演示 / 回归基线            · 知识缺失 → 生成 kb 候选文档      · export → bakeoff 样本
  · 好的步骤话术 → plans.yaml 改写候选              · 检索错配 → scope / 改写规则       · export → inspection 场景
  · 相似工单 → kb_tickets 入库候选                  · 计划不对 → plans / fault_cards    · CI：haike-replay verify
                                                   · 模型输出差 → bakeoff 加样本         + make inspect 必过
                                                   · 规则误触 → rules 配置
                                                   · 产品未识别 → products 别名
          └──────────────── 修复后回归 → cases.status = fixed，fixed_in = release id ────┘
```

仓库已有的工具全部复用：录制包格式（`app/replay/package.py`，键不含 session / 时间，可从 analytics + JSONL 重建）、bake-off 样本与四项指标（`app/bakeoff`）、巡检场景（`app/inspection/scenarios.py`）、知识灌库与 manifest（`haike-kb ingest`）、发布冻结（票 49）。新增只是「案例 → 这些格式」的导出器。

### 9.2 标注模型

- `verdict`：good / bad / review。
- `reason_tags`（多选，固定枚举便于统计）：`knowledge_missing` 知识缺失、`retrieval_mismatch` 检索错配、`wrong_plan` 计划不对、`bad_step_wording` 步骤话术差、`model_quality` 模型输出差、`model_fallback` 降级导致、`rule_false_positive` 规则误触、`product_unrecognized` 产品未识别、`emotion_mishandled` 情绪处理不当、`latency` 太慢、`ui_flow` 交互问题、`user_abandoned` 用户中途离开、`exemplary` 值得沉淀。
- 自动候选（不自动定性，只进 review 队列）：升级原因 ∈ R1*/R2/R5/R7；`knowledge_status = no_match` 却给出步骤；同会话 `not_solved` ≥ 2；`fallback_used` 且用户随后升级；首可见 > P95 × 2；错误 / 超时；连续两次 rediagnose。

### 9.3 复盘看板（Cases 页）

- 坏案例按 reason_tag × 品类 × 周 的热力 / 趋势；open → exported → fixed 漏斗；每个 release 修了多少、回归通过多少。
- 好案例按品类 / 故障计划归档，可一键「转录制包」用于演示与基线。
- 每个案例页 = 会话旅程页 + 标注面板 + 导出记录 + Langfuse 深链。

### 9.4 与迭代节奏的衔接

- 周复盘：从 Cases 拉 open 的 bad 案例 → 归因 → 派工到 config（plans / rules / products / fault_cards）、知识（kb 候选）、提示词（prompts/）、模型（bakeoff）。
- 每次发布前：`make replay-verify` 对所有已导出 good 案例 + `make inspect` 覆盖所有已导出 bad 案例场景；不过不发（接入票 49 的 ci-local）。
- 金标集版本随 `{prompt_ver, models_ver, kb_ver, rules_ver}` 一起冻结（录制包清单已有该四元组）。

## 10. 性能与扩展

| 量级 | 会话 / 日 | node_runs / 月 | 措施 |
| --- | --- | --- | --- |
| 现在（黑客松 / 试点） | < 1 k | < 1 M | 直接 SQL + 索引即可；rollup 可选 |
| 试运营 | 1–10 k | 1–10 M | 开启 daily_rollups（面板只读 rollup）；`created_at` 改 BRIN；messages / model_calls 30 d TTL |
| 规模化 | > 10 k | > 10 M | `analytics` 按月分区（`pg_partman` 或原生声明式）；或迁 ClickHouse（Langfuse 已带一套，可评估复用）；查询层只换实现 |

写入路径：每 run 约 8–12 个节点 + 3–6 次模型 + 2–4 次检索 ≈ 20 行，批量 `executemany` 每秒一次；10 k 会话 / 日 × 4 run ≈ 1 M 行 / 日，单机 PG 轻松。队列上限 2000、满即丢并计数，主链路无感。

读路径：列表与详情都按索引点查；面板按天预聚合；`flow` 聚合在 node_runs 上 `(prev_node,node)` 索引 + 时间范围，千万级也在百毫秒级；再大读 rollup 里的边计数（`dim_kind='edge'`）。

连接池：复用 `session_pool`（`DB_POOL_MAX=10`），sink 单连接批写；管理端查询走同池，`statement_timeout=5s` 防慢查询拖垮在线接口；量大时给 admin 单独一个只读池 / 只读副本。

## 11. 需要你拍板的决策

| # | 决策 | 建议 |
| --- | --- | --- |
| D1 | analytics 是否存脱敏后的用户问句 / 助手文本（30 d） | 存，默认开；票 48 的 PII 口径沿用 `privacy.sanitize`，并把 `ANALYTICS_STORE_TEXT` 写进运行手册 |
| D2 | 解决率主口径 | §8 的「自助解决率」为主，闭环率为辅，面板两个都显示 |
| D3 | user_ref 从哪来 | 本期加列 + `POST /sessions` 接受可选 `X-User-Ref`；接入渠道后由网关注入 |
| D4 | 管理端鉴权 | 本期 ADMIN_TOKEN 门 + sessionStorage；生产在票 46 反代加 SSO / Basic，后续再做角色 |
| D5 | 面板自建 vs Grafana / Metabase | 旅程 / DAG / 案例自建（领域特有）；纯 KPI 面板先自建最小集，业务自助分析时再接 Metabase 读 analytics schema |
| D6 | 自动候选规则是否上线 | 上，但只进 review 队列，不自动定性 |

## 12. 分期（详见 task_plan.md）

1. **P1 数据底座**（后端）：迁移 0004、sink、三个接入点、derive、backfill、独立 TTL、health 字段、测试。
2. **P2 Admin API**：auth、sessions / journey / graph / metrics / flow、契约导出、测试。
3. **P3 管理端前端**：第二入口、TokenGate、Dashboard、Sessions、SessionJourney（时间线 / 瀑布 / DAG）、Flow。
4. **P4 案例闭环**：cases 表与 API、标注 UI、导出器（replay / bakeoff / inspection / kb 候选）、Cases 页、CI 接入。
5. **P5 性能与运维**：rollup 任务、告警、runbook、size 门槛、（按量）分区。
