# 官方 63 案例修复开发规格（第一批）

状态：开发规格，尚未实施。依据：

- Codex 测评报告 `docs/codex/2026-10-09_官方63案例全量测评与改进判断.md`（I1–I9）
- Codex 复核 `docs/codex/2026-10-09_7.1资料质量复核与正确处理.md`（只取两点：T50 不补否定词、T46 外接软管步骤屏蔽）
- Codex 设计 `docs/codex/spec_2026-10-09_t9_request_completion.md`（交接成功话术只能依据持久化结果；复用 task_queue 与案件存储，不建新表）
- 本会话代码核对 `docs/planning/2026-10-09-1605_official-63-remediation/findings.md`

已定决策（2026-10-09）：D1 过保后继续官方自助排障；D2 事实问句卡为选项加短答；D3 新增 `parts_purchase` 意图并一律人工交接；D4 今日两轮改动已提交（fbefd7a、bf29496），本规格在其之上实施。

术语：事实（fact）= 从用户原文抽取、带逐字引文的陈述；适用性（applicability）= 候选 Q&A 方案能否解释当前现象并满足入口前提；任务（task）= task_queue 里一条诉求及状态；交接（handoff）= 案件进入人工审核队列并写摘要。

## 0. 范围

| 批次 | 范围 | 本规格 |
|---|---|---|
| 1 | 处理方向与结束条件：I1 I2 I3 I6 I7，评测标签 | 详细（§1–§7） |
| 2 | 知识节点类型与卡片协议：I4 I5 | 概要（§8），实施前另出规格 |
| 3 | 交接展示与答复收敛：I8 I9 | 概要（§9） |

改动按机制做，禁止按工单编号特判；工单编号只出现在测试与注释。

## 1. 事实模型：来源、对象、极性、方向（修 I1 I3）

### 1.1 问题

- T11：`Click to contact customer service` 来自 App 推送字段，被当成用户主动要人工。`reduce.py:382` 只校验引文在原文里，不看引文落在哪个字段。
- T50：`the left one does work` 字面肯定，系统当左侧故障直接发操作卡。
- T52：「盒子自己充不进电」与候选「盒子给泵充电」对象层级不同，无字段可核对。
- T61：「提前两小时」「记录未保存」被改成「定时无法启动」，无方向字段。
- T27/T36/T37/T31：用户自述已做的排查无记录类型；T31 的「despite wiping clean」被解释成操作条件变更。

### 1.2 改动：`conversation/interpret.py`

`FactCandidate` 增加：

```python
kind: Literal["symptom", "observation", "preference", "context", "action_taken"] = "symptom"
subject: str | None = None        # 部件或对象原话
polarity: Literal["affirmed", "negated", "uncertain"] = "affirmed"
timing: str | None = None         # 时间方向/时机原话：2 hours before / after repair / intermittent
```

INSTRUCTION 追加（不改既有句子）：

- subject 填用户提到的部件或对象原话；polarity 按字面：肯定 affirmed、否定 negated、字面与语境矛盾（「does work」却在求助）uncertain，不改写原话。
- timing 只填用户给出的时间方向或时机，没有留空。
- 用户说已做过的排查抽为 kind=action_taken，value 写动作与对象；它不是 operation_update，也不是 step_feedback。
- 设备推送、错误提示里的「联系客服」不是用户请求人工；human_request_quote 只能引用用户自己写的句子。

`INTERPRET_PROMPT_VERSION = "2026-10-09.3"`。

### 1.3 改动：`conversation/reduce.py`

1. 新增 `device_message_spans(text)`：返回 `parse_message(text).fields` 的 `push`、`description` 值（两者相同或互为前缀时只保留一段）。
2. fact 写入增加 `subject`、`polarity`、`timing`、`source`。`source`：引文 normalize 后完整落在某 span 内 → `device_message`，否则 `user_statement`。现有 `source_kind` 不动。来源只影响 R3 校验和 §4 澄清判断，不影响症状进检索（T22/T30 的设备文案仍是有效症状）。
3. `request_human` 校验：引文必须在原文且不在任何 device_message span 内；不满足时，原文有错误码或 symptom → 降为 `report_problem`，否则沿用现有 complaint/unknown 降级。
4. `issue["symptoms"]` 与 title 只收 `polarity != "negated"` 的 symptom；negated 留在 facts。
5. `meaning.operation_update.quote` 与某条 action_taken 引文重叠时丢弃 operation_update。

`conversation/l3_intents.py fallback_interpretation`：R3 命中词只出现在 device_message span 内时不设 request_human。R3 词表不改。

### 1.4 测试

- `tests/test_conversation_reduce.py`：设备推送句不构成 R3；用户自写 human 请求仍 R3；negated 不进 symptoms；action_taken 压制 operation_update。
- `tests/test_conversation_official_tickets.py` `test_t11_device_prompt_gets_the_official_eb1l_steps`：模型给 request_human 引推送句 → 首卡 `qa_rv_0481`。

## 2. 适用性核对用结构化事实（修 I2 I3）

### 2.1 问题

`synthesize.py` 只把症状字符串给模型，不给已解析错误码和新字段；supported 完全信模型。精确同码命中仍要过模型门槛，T18/T30 因此波动。

### 2.2 改动

`sessions/graph.py retrieve`：`exact["evidence"]` 非空且唯一 guide 的 `kind == "steps"` → 直接 `plans_ranked=[{plan_id, confidence 1.0, source "exact_code", supported_symptoms: [push 文本或码]}]`，跳过 synthesize。同码多条仍交模型。`code_miss`、`warranty` 分支不变。

`diagnose/synthesize.py`：

- 新入参 `facts`（active facts 全量）、`error_codes`；提示加 `<data kind="structured_facts">`（kind / subject / polarity / timing / value 表）与 `<data kind="error_codes">`。
- `Hypothesis` 加 `matched_subject`、`matched_timing`。
- `filter_hypotheses` 确定性核对，任一不过 → 降为 needs_confirmation 并按模板补 clarification_question：
  1. supported_symptoms 对应 fact 的 polarity 为 uncertain → `You mentioned "<quote>". Which side or part has the problem, and what is it doing?`
  2. 候选 `symptom_codes` 非空、用户 error_codes 非空且无交集 → not_applicable。
  3. 用户 symptom 有 timing，假设 matched_timing 为空或矛盾（用户含 before/early/ahead/提前 而候选标题含 failed to start/not start）→ `You said it happened <timing>. Is that right, and does the app show any warning at that moment?`
  4. subject 与 matched_subject 都非空且互不包含 → `Is the problem with the <subject> itself (its own charging light or power input), or with how it works with other parts?`
- clarifications 过滤：问题文本含用户已给错误码 → 丢弃（T18 不再问 3212 还是 3202）。
- INSTRUCTION 追加：候选只重复 action_taken 的动作则 not_applicable，否则 rationale 说明新增检查点。

### 2.3 测试

新文件 `tests/test_applicability_facts.py`：精确同码直通（T18/T30，synthesize 调用 0 次）；uncertain 极性强制澄清（T50）；timing 矛盾不 supported（T61）；subject 层级不符问输入供电（T52）；澄清不问已知码；同型号异码 not_applicable。

## 3. 首轮 operation_update 不绕过检索（修 T31）

`graph.py route_entry`：`operation_changed` 且 `plans_ranked` 为空且无执行历史 → `disambiguate`，否则 `reassess`。测试：T31 原文走 retrieve，不出现 R2。

## 4. 信息不足先澄清再交接（修 T58 T60）

`graph.py _diagnose_outcome` 增加入参 `issue_facts`、`error_codes`：plans_ranked 空、无 clarifications、`knowledge_status == "no_match"`、无 affirmed symptom、无错误码 → `_decision={"outcome":"clarify","reason":"symptom"}`，`diagnose_outcome.mode="clarify"`，复用 `MAX_CLARIFICATIONS`；耗尽后 R5。`described()` 只负责放行检索。测试：T60 原文 no_match → 先澄清，两轮无效后 R5。

## 5. 过保只关闭免费服务任务（修 T51 T53）

`sessions/l3.py propose()` 过保与非授权经销商分支：改为 `{"stage":"done", "case_status":…, "completed_task_intent": INTENT_OF_REMEDY.get(remedy, "replacement_request"), "task_outcome":"done", "l3_route":"advance_tasks"}`；队列有 pending `report_problem` 时文案追加 `I can still walk you through the official checks for this issue.`。`advance_tasks` 现有逻辑会提升 report_problem 进 disambiguate。测试：T51（Anker014，replacement + report_problem + 症状）→ 过保文案后出现步骤卡或症状澄清，最终队列无 pending/active；现有单诉求过保测试不变。

## 6. 交接摘要从事实记录生成（修 T9 T22 T34 T60）

### 6.1 契约

`contracts/haike_contracts/common.py`：

```python
class PendingRequest(Strict):
    intent: str
    quote: str
    status: str

class HandoffBusiness(Strict):
    kind: Literal["device_fault", "order_change", "parts_purchase", "warranty_review", "safety", "unknown"]
    known: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    pending_requests: list[PendingRequest] = Field(default_factory=list)
```

`EscalationSummary.business: HandoffBusiness | None = None`。`make contracts` 后提交产物。

### 6.2 后端

`escalation/summary.py`：

- `problem` 回退链：symptom facts → `parse_message(text).problem_text` → issue.title（非占位）→ 「（尚未记录具体故障现象）」。
- `official/message.py`：`Inlogland`、`Land van accountregistratie` 移到新字段 `login_country`；`first_message_facts` 渲染为「客户登录/注册国家」，不再是购买渠道。
- `handoff_business(state)`：kind 由 R4 / NOT_EXECUTABLE remedy / parts_purchase / warranty / symptom 依次判定；known 含订单号、包裹状态、条件原话（order_change 任务 quote）、产品、症状（含 subject/timing）、已做操作；missing 按 kind 固定清单减 known；pending_requests 取队列 pending/active/waiting_human。
- `summary_to_text` 加「【业务】」行。

`sessions/l3.py advance_tasks`：消费类任务完成、案件 awaiting_approval 且已有 latest_summary 时递增 issue_revision，`commit_issue` 现有逻辑触发 `summarize(summary_refresh=True)`（T9 物流事实并入摘要）。

### 6.3 前端

`SummaryCard.tsx` 与 `summaryToText` 渲染 business 四行；`Cards.test.tsx` 更新。

### 6.4 测试

`tests/test_escalation_summary.py`：problem 回退（T22）；login_country 不是购买渠道；order_change 的 business 保留条件原话（T9）。`tests/test_conversation_l3.py`：T9 交接后 consult 完成，最新 handoff_summary 的 business.known 含包裹状态。现有「尚未记录具体故障现象」断言按夹具是否有正文调整。`contracts/tests/samples.py` SUMMARY 加 business。

## 7. 评测标签与驱动器

`data/eval/tickets/cases.yaml`：

| 案例 | 改动 |
|---|---|
| T50 | `sop: clarify`；note：原话为肯定句，须先确认故障侧与现象 |
| T52 | `sop: clarify`；note：先区分盒子自身供电与盒子给泵充电；加 `first_card_forbid: [bp-0067, bp-0039]` |
| T61 | 删 qa_gold；`sop: clarify`；note：提前两小时与记录缺失须保留 |
| T46 | qa_gold 删 bp-0102/bp-0043；note：异响不等于无吸力 |

`evaluation/live_tickets.py`：

- `stage == "done"` 且 task_queue 有 pending/active → forbid `done_with_pending_tasks`。
- R3 终点要求 understand 摘要新增的 `human_request_source == "user_statement"`。
- `first_card_forbid`：首张 step_card 的 plan_id 命中 → forbid。

`tests/test_eval_tickets.py` 的 `sop_deterministic` 数按实际值更新并在 commit 说明。

## 8. 第二批概要（I4 I5）

- `official/qa_index.py` `Step.kind: question | action | statement | material_request | handoff`，离线规则分类；`data/official/qa_overrides.yaml` 按 `qa_id + step_no` 覆写 kind、question 选项、`disabled`（T46 外接软管步骤屏蔽）。
- `plans/models.py` `PlanStep.kind / options / branches`；只有 action 生成三条反馈边。
- 契约：`TroubleshootStep.kind/options`、`StepFeedbackPayload.answer`；`router._kind_allowed` 按 kind 校验。
- `guide/verify.py`：question 回答写成 observation fact；只有 action 的 not_solved 计 executed；material_request 暂缺进 missing。
- `guide/steps.py`：与 action_taken 匹配的步骤跳过并记 `step_dropped: user_reported`。
- 前端 `StepCard.tsx` 按 kind 渲染；驱动器遇 question 卡停止。

## 9. 第三批概要（I8 I9）

- T47：`answers.py` 比对客户 SKU 与订单商品 SKU，不一致时说明无该配件发货记录并索取配件订单/案件号。
- T63：Intent 加 `parts_purchase`，PRIORITY 1 级，NOT_EXECUTABLE，交接 kind=parts_purchase。
- T35：`prompts/reply.py` 证据标签改序号，INSTRUCTION 限定只答所问机制；`conversation/reply.py` 流式失败发 aborted、新 message_id 发状态文案、写 `last_error`；前端重试入口。

## 10. 验收

1. `make lint`、相关 pytest、`npm --prefix frontend run typecheck`、涉及契约时 `make contracts-check`。
2. `make up` 后用 live_tickets 跑 63 单，口径沿用 `docs/planning/2026-10-09-1515_full-official-evaluation/criteria.md`。
3. 8 个错误案例各加三条变体：同义改写、否定表达、诉求顺序互换。
4. 回归保护集保持首测结论：T1–T10、T12、T13、T14、T32、T45、T55。
5. 门槛：8 个错误案例无同类错误；done 时无 pending；R3 只来自用户原话；每单能指出当前结果或需补事实。

## 11. 文件清单（第一批）

| 文件 | 改动 |
|---|---|
| conversation/interpret.py | FactCandidate 新字段；INSTRUCTION；版本号 |
| conversation/reduce.py | device_message_spans；source；R3 校验；negated；action_taken 压制 operation_update |
| conversation/l3_intents.py | fallback R3 过滤 |
| official/message.py | login_country |
| diagnose/synthesize.py | 新入参；提示；Hypothesis 字段；确定性核对；澄清过滤 |
| sessions/graph.py | 精确同码直通；route_entry；_diagnose_outcome 症状澄清；understand 摘要 human_request_source |
| sessions/l3.py | propose 走 advance_tasks；advance_tasks 摘要刷新 |
| escalation/summary.py | problem 回退；login_country；handoff_business；summary_to_text |
| contracts/common.py + 生成产物 | HandoffBusiness / PendingRequest |
| frontend SummaryCard.tsx、Cards.test.tsx | business 四行 |
| data/eval/tickets/cases.yaml | §7 |
| evaluation/live_tickets.py | done_with_pending_tasks、R3 来源、first_card_forbid |
| tests | §1.4 §2.3 §3 §4 §5 §6.4 |

## 12. 不做

通用流程编排器；875 条知识逐条复核（T46 软管等按需覆写）；模型做步骤分类；独立任务表或工作流引擎。
