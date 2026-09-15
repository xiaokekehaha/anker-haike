# 第五步：案件生命周期与最小人工协同回路

## 1. 为什么要独立的案件对象
会话 / run 是分钟级，一次 run 的 `done(completed)` 只表示这轮结束。退换修、物流、人工审批是小时到天级，需要独立状态、责任人、外部单号与结案条件（差距分析 §4.3；[service-flow-gap-analysis](../2026-09-12_service-flow-gap-analysis/comparison.md) 差异 3）。

## 2. 案件模型
```sql
cases(
  case_id uuid pk, session_id text, issue_id text, sku text, category text,
  status text, complaint_risk bool default false, priority text,   -- normal|high
  policy_decision jsonb, proposal jsonb, chosen_option_id text,
  owner text, external_refs jsonb,        -- {service_order_no, tracking_no}
  opened_at, updated_at, closed_at timestamptz, reopened_count int default 0)
case_events(id bigserial pk, case_id uuid, seq int, type text, payload jsonb, actor text, at timestamptz)  -- actor: user|system|agent:<id>
human_decisions(decision_id uuid pk, case_id uuid, actor text, decision text,   -- approve|reject|request_info
  edited_proposal jsonb, override_reason text, note text, at timestamptz, consumed_input_id text)
satisfaction_ratings(id bigserial pk, session_id text, issue_id text, case_id uuid null, score int check(score between 1 and 5), comment text, at timestamptz, unique(session_id, issue_id))
```
状态机：
```
open → diagnosing → proposing → awaiting_confirmation → (authorize)
   ├─ pass → executing → tracking → closed
   └─ fail / needs_human → awaiting_approval → approved → executing …
                                             └ rejected → proposing | closed_unresolved
closed → reopened（用户再次求助同一 issue 或结果未达成）→ tracking | proposing
任意 → escalated_summary（R3/R4/R7/R8 路径，只交接不办理）
```
- 何时创建：进入 `service_context`（即开始考虑补救）或 `await_human` 时 `CaseService.open()`；纯排障并解决的 issue 不建案件（托管率分子里算 resolved）。
- 结案条件：`tracking` 中外部状态到达终态（service_order status=shipped/completed）且用户确认（RatingCard 或「已收到」意图），或人工结案。
- 重开：同 issue 再次出现 report_problem / not_solved，或用户否认「已解决」。

## 3. 事件与快照
- 事件 `case_changed{case_id, status, complaint_risk, priority, owner?, reason, external_refs?}`；每次状态迁移发一次，前端 CaseStatus 条目 upsert。
- 快照 `CaseStatusItem{case_id, status, complaint_risk, external_refs, updated_at}` 挂 issue。
- `EscalationSummary` 增量字段：`case_id`, `policy_decision_brief{policy_id, within_warranty, needs_human_reasons}`, `recommended_options[]`（与 proposal_card 同结构）, `gate_result`, `task_queue`, `emotion_track`, `draft_reply`（确定性模板拼出的给用户的回复草稿，人工可改）。

## 4. 最小人工回路
### 4.1 后端 API（`app/admin/router.py`）
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/admin/api/cases/queue?status=awaiting_approval&priority=` | 队列：案件 + 摘要 + 等待时长；complaint_risk 置顶 |
| GET | `/admin/api/cases/{case_id}` | 详情：摘要、policy_decision.conditions、gate_result.checks、proposal options、时间线（复用 ReadonlyTimeline）、执行记录 |
| POST | `/admin/api/cases/{case_id}/decision` | `{decision: approve|reject|request_info, option_id?, edited_option?, override_reason?, note}`；写 human_decisions，并向会话投递 `human_decision` 输入 |
| POST | `/admin/api/cases/{case_id}/close` `/reopen` | 人工结案 / 重开 |
鉴权沿用管理台现有 basic auth（deploy/proxy）；`actor` 取请求头用户名；并发用 `cases.updated_at` 乐观版本，冲突 409。

### 4.2 决定如何回到会话
`POST decision` → `sessions._accept()` 接受一条 `kind=human_decision` 的输入（新增到 `sessions/inputs.py`，`entry="human_decision"`，payload 含 decision_id），走正常 run：`understand` 跳过语义解释（非用户文本）→ `route_entry → apply_human_decision`：
- approve：`proposal.chosen_option_id = option_id`（若 edited_option，则以人工版本覆盖并标 `source: human`）→ `authorize`（人工批准视为通过政策项与幂等以外的检查仍执行）→ `execute`。
- reject：`propose` 重新生成不含被拒项的方案，或无方案 → `summarize`（交接）；用户可见解释含人工备注。
- request_info：`dialogue` 向用户提问（备注即问题）；案件回到 awaiting_confirmation。
用户端在等待期间看到 CaseStatus「等待人工审核（预计 X 分钟）」；用户此时发消息走正常 understand，不打断案件。

### 4.3 前端（管理端）
- `pages/Approvals.tsx`：队列表 + 筛选（状态 / 优先级 / 情绪）+ 认领。
- `pages/CaseDetail.tsx`：左时间线；中方案卡（同用户端 ProposalCard 组件复用，加「编辑」）+ 政策条件表 + 门检查表；右决策面板（批准 / 拒绝 / 要信息 + 备注 + 覆盖理由必填）。
- Dashboard 增加：待审批数、平均等待、complaint_risk 数。

### 4.4 前端（用户端）
- `CaseStatus.tsx`：状态条（等待人工 / 办理中 / 跟踪中 / 已结案）+ 外部单号。
- `RatingCard.tsx`：1–5 星 + 可选评论；提交 `rate_satisfaction`。

## 5. 与既有模块的关系
- analytics：`sessions` 投影增加 `case_id`, `case_status`；outcome 分类新增 `executed_closed`, `awaiting_human`（终态判定见 07 §3）。
- service-quality-loop 的 `quality_feedback` 与本处 `satisfaction_ratings`：P0 先落后者，字段与前者兼容（actor=user, type=satisfaction），P1 合并到 quality 表族。
- retention：cases / human_decisions 不随会话 24 h 清理；按 case 关闭后 N 天清理，删除会话接口级联去标识化（保留统计不保留原文）。

## 6. 测试
- 状态机单测：非法迁移拒绝；reopen 计数；closed 后 rate 仍可写。
- HITL 集成：A6 全链（gate fail → 队列可见 → approve → execute → 回执）；reject → 备选方案；request_info → 用户问答后回到 proposing。
- 并发：两个管理员同时决定 → 一个 409；同一 decision_id 重投递幂等。
