# 官方 63 案例问题修复方案

依据：`docs/codex/2026-10-09_官方63案例全量测评与改进判断.md`（I1–I9）与本目录 findings.md 的代码核对。本文是方案与计划，尚未实施。

## 1. 总体判断

同意测评文档的三个决策：不重写、改业务结束条件、保留一次一步但拆卡片类型。代码核对后把九个问题归到四个机制缺口，修复按缺口做，不按工单编号写例外：

| 缺口 | 现状 | 涉及问题 |
|---|---|---|
| G1 事实没有结构 | `FactCandidate` 只有 value/quote，没有部件、极性、方向、来源；synthesize 只看症状字符串，连已解析的错误码都不给 | I1 I2 I3 I5 |
| G2 结束与升级条件只看单一信号 | 过保直接 `stage=done`；首轮 operation_update 走 reassess 后无候选即 R2；no_match 直接 R5 | I2(T31) I6 I7 |
| G3 文档段落等于操作步骤 | `Step` / `PlanStep` / `TroubleshootStep` 没有类型，三按钮一刀切 | I4 I5 |
| G4 交接与答复从单一字段生成 | 摘要 problem 只取 symptom facts；无业务类型字段；回复提示带内部 ID、流式失败伪装完成 | I7 I8 I9 |

前提：今日工作树里 round5 routing fix 与 diagnosis recovery 两轮改动（applicability 门槛、候选恢复、真实入队）尚未提交，测评镜像已包含它们。本方案在其之上做，第一步先跑 `scripts/ci-local.sh` 并提交这些改动，否则后续每批的 diff 无法单独评审。

## 2. 第一批：处理方向与结束条件（I1 I2 I3 I6 I7）

### 2.1 事实来源与极性（G1，修 I1 I3）

扩展 `conversation/interpret.py` 的 `FactCandidate`：

```
kind: symptom | observation | preference | context | action_taken
subject: str | None        # 部件或对象：charging case / pump hub / left side / schedule
polarity: affirmed | negated | uncertain   # "does work" 字面肯定但语境像笔误 → uncertain
timing: str | None         # early / late / never / intermittent / after_repair 等自由短语
source: user_statement | device_message | quoted_third_party
```

- `source` 由服务端判定，不信模型：`reduce.py` 归约时用 `parse_message().fields["push"/"description"]` 与原文位置判断引文落在设备推送字段里就标 `device_message`。T11 的 `contact customer service` 来自 push 字段。
- `reduce.py:382-387` 的 `request_human` 校验改为：`human_request_quote` 必须逐字在原文、且不落在 device_message 片段内；否则降级为 `report_problem`（原文有故障码）或 `complaint`。R3 词表不删，`rules.check_in` 兜底解释同样加这一来源判断。T45 安全路径与 `RequestHumanAction` 卡片动作不受影响。
- `polarity=uncertain` 的症状不能作为 `supported_symptoms`；synthesize 看到唯一症状不确定时只能发 needs_confirmation。T50 由此得到澄清「which side has the problem, and what is it doing」。
- `subject` 和 `timing` 作为适用性核对的输入（2.2）。

### 2.2 适用性核对用结构化事实（G1，修 I2 I3）

`diagnose/synthesize.py`：

1. 提示输入补三项：`parse_message().codes` 与 `state.error_codes`；结构化事实表（subject / polarity / timing / source）；`action_taken` 事实列表。现在 `symptoms` 只有字符串。
2. 输出 `Hypothesis` 增加 `matched_subject`、`matched_timing`，`filter_hypotheses` 做确定性核对：
   - 用户症状 `polarity=uncertain` → 该方案最多 needs_confirmation。
   - 候选 Q&A 标题含错误码而用户错误码不同 → not_applicable（同码才可 supported；无码不拒绝，沿用今日规则）。
   - 用户 `timing` 与候选方向矛盾（T61「提前」对「无法启动」）→ needs_confirmation，clarification_question 必须引用用户的 timing。
   - `subject` 与候选标题主语不同层级（T52「盒子自身」对「盒子给泵」）→ needs_confirmation，问盒子插电后的指示灯。
3. 同型号同错误码的精确命中（`exact_code_hits` 返回 `kind=steps` 的 guide）直接 supported，`supported_symptoms` 取该码对应的症状，不经模型判适用性。T18/T30 的 3212/E4 由此稳定进入方案；T13 的 code_miss 分支不变。
4. `clarification_question` 不允许询问用户原文已给出的事实（已解析错误码、已给型号）。服务端在 `_diagnose_outcome` 里过滤：问题文本若包含已知错误码就丢弃该澄清，直接取 supported 候选或 R5。

### 2.3 首轮 operation_update 不得绕过检索（G2，修 T31）

`sessions/graph.py:1397` `operation_changed → reassess` 加条件：`plans_ranked` 为空且本问题从未进入 guide 时，走 `disambiguate`。`action_taken` 事实替代把「despite wiping clean」解释成操作条件；`operation_update` 的提示词补一句：用户描述已做过的排查不是操作条件变更。

### 2.4 信息不足先澄清再交接（G2，修 I7 T58 T60）

`_diagnose_outcome`：`knowledge_status=no_match` 且 issue 没有 `polarity=affirmed` 的 symptom 事实、没有错误码时，先走 symptom 澄清（沿用 `MAX_CLARIFICATIONS=2`），耗尽再 R5。`described()` 的「≥6 词」兜底只用于放行检索，不再作为可交接的依据。

### 2.5 过保只关闭免费服务资格（G2，修 I6）

`sessions/l3.py:335-345`：过保分支把当前 `replacement_request` 任务置 done，返回 `l3_route=advance_tasks`，不再直接 `stage=done`。`advance_tasks` 提升 pending 的 `report_problem` 后进入排障；回复文案加一句「warranty service isn't available, but I can still walk you through the official checks」。`unauthorized_dealer` 分支同样处理。

需要确认的业务边界（D1）：SOP 有过保委婉拒绝分支。本方案默认过保后继续提供官方自助指导；若业务决定不继续，则改为明确关闭该任务并说明，不能留 pending。两种都不允许「仍有待办却 done」。

### 2.6 摘要从事实记录生成（G4，修 I7 I8 T9 T22 T34 T60 T63）

`escalation/summary.py`：

- `problem` 字段：无 symptom 事实时回退到 `parse_message().problem_text`，再回退 issue 标题；禁止「尚未记录具体故障现象」与原文有现象并存。
- `official/message.py` LABELS 拆分：`Inlogland` / `Land van accountregistratie` 归 `login_country`，不再渲染为「购买渠道」。
- `EscalationSummary` 增加 `business: HandoffBusiness`（契约模型，`make contracts`）：

```
kind: device_fault | order_change | parts_purchase | warranty_review | safety
known: dict[str, str]      # 订单号、包裹、条件、产品、症状、已做操作、缺件名称
missing: list[str]
pending_requests: list[{intent, quote, status}]
```

  按任务类型填字段：order_change 带订单/包裹/条件原话（T9「if you have not shipped, don't」）；device_fault 带 subject/polarity/timing 和 action_taken；parts_purchase 带型号与部件。
- `advance_tasks` 完成消费类任务后，若案件已 awaiting_approval，触发一次 `summary_refresh`，把物流事实并入摘要（T9）。

### 2.7 评测标签与驱动器（第一批前置）

`data/eval/tickets/cases.yaml`：T50 改 `sop: clarify`，note 改为「原话歧义，须澄清哪侧/什么功能」；T52 qa_gold 改为「先确认盒子输入供电」的澄清或 bp-0039 之外的盒子自身充电条目，验收检查首卡不得是盒子→泵接触；T61 去掉 rv-0551/rv-0522，期望澄清保留「提前两小时」「记录缺失」；T46 qa_gold 去掉吸力条目，期望首卡为事实问句。
`evaluation/live_tickets.py`：驱动器遇到 `kind=question` 卡停止（第二批生效）；`sop_passed` 增加断言「stage=done 时 task_queue 无 pending/active」；R3 终点要求 `human_request_quote` 的 source 为 user_statement。

## 3. 第二批：知识节点类型与卡片协议（I4 I5）

### 3.1 离线分类（G3）

`official/qa_index.py` 的 `Step` 增加 `kind: question | action | statement | material_request | handoff`，规则在构建索引时确定，不调模型：

| 判定 | kind |
|---|---|
| 以 `?` 结尾，或以 Is/Does/When/Which/Are 开头 | question |
| 含 record a video / upload / send us a photo / provide the SN | material_request |
| `Step N:` 标题行、以 If … persists / contact … / hardware service / warranty 结尾的结论 | statement 或 handoff（含 contact/service 为 handoff） |
| 其余 | action |

`data/official/qa_overrides.yaml` 允许对高频条目按 `qa_id + step_no` 人工覆写 kind 与 question 选项（bp-0123 的「持续/间歇」「启动时/泵吸时/高速时」）。通用可视化编排器不做。

### 3.2 计划与契约

- `plans/models.py` `PlanStep` 增加 `kind`、`options: list[str]`、`branches: dict[option, step_id]`（question 用）；`next_on` 只对 action 生效。statement 不等待反馈，随下一个 action 卡的 `context` 一起展示；handoff 直接走 escalate R2。
- 契约：`TroubleshootStep.kind`、`options`；`StepFeedbackPayload` 增加 `answer: {option: str | None, text: str | None}`，question/material_request 卡提交 answer 而不是 feedback；`PendingKind` 不新增，复用 step_feedback 的 pending，`router._kind_allowed` 按 kind 校验 payload。
- `guide/verify.py`：只有 action 的 not_solved 计 `executed`；question 的 answer 写成 `observation` 事实（source=user_statement，subject 取问题对象），按 `branches` 选下一步，没有分支就继续下一步；material_request 的「暂缺」记入 `missing`，流程继续并保留待补状态。
- 前端 `StepCard.tsx` 按 kind 渲染：question 为选项按钮加短答输入；material_request 为上传或「暂时没有」；statement 无按钮；action 维持三按钮。`Timeline.tsx` 的 `POINTER` 文案随 kind 变化。

### 3.3 已做操作进入排障历史（I5）

- `action_taken` 事实进入 `prepare_step`：步骤 `instruction` 与某条 action_taken 语义匹配（同部件 + 同动作词表：clean / replace / restart / refill）时跳过并记 `step_dropped: user_reported`；跳过后若计划全部耗尽，交接摘要列出「用户自述已做」。
- synthesize 的提示拿到 action_taken 列表，`rationale` 必须说明新增检查点；T27/T36 的「仍持续异响」作为 symptom + action_taken 组合，候选若只是重复已做动作就 not_applicable。

## 4. 第三批：交接展示与答复收敛（I8 I9）

- T47：`conversation/answers.py` 渲染物流前比对客户提到的 SKU 与订单商品 SKU；不一致时加一句「the order record shows T8D04121 (main unit); I don't see a separate shipment for the T8D02181-80 hub」，并把「是否售后补寄」作为澄清。
- T63：Intent 枚举增加 `parts_purchase`，`PRIORITY` 归入 1 级，`NOT_EXECUTABLE` 处理（无配件目录接口），交接 business.kind=parts_purchase 带型号与部件；摘要同时保留故障与清洁效果诉求。
- T35：`prompts/reply.py` 不再给模型 8 位证据 ID，改用序号标签 `[1]`，`REPLY_INSTRUCTION` 增加「只回答被问的机制与必要例外，不列其他错误码」；`conversation/reply.py` 流式失败时发 `message_end status=aborted`，用新 message_id 发状态文案并写 `last_error`，前端显示重试入口。
- T9 页面「跟踪办理进度」在演示配置里弱化，后台审批不删。

## 5. 验收与回归

每批完成后：

1. 单测：FakeChatModel + 假知识库，新增文件按 `tests/test_<模块>_<问题>.py`，回归旁注明 T 编号。
2. `make lint`、`npm --prefix frontend run typecheck`、`make contracts-check`（第二批）。
3. `make up` 重建镜像后用 `evaluation/live_tickets.py` 跑全部 63 单，口径沿用 `../2026-10-09-1515_full-official-evaluation/criteria.md`；对 8 个错误案例各加三条变体（同义改写、否定表达、诉求顺序互换）。
4. 回归保护集必须保持首测结论：T1–T10、T13、T32、T45、T55、T12、T14。
5. 门槛：8 个错误案例无同类错误；事实问句不计 executed；`stage=done` 时无 pending；每单能指出当前结果或需补的事实。重复运行只用于看稳定性。

## 6. 文件清单

| 批次 | 后端 | 契约 / 数据 | 前端 |
|---|---|---|---|
| 1 | conversation/interpret.py、reduce.py、request_constraints.py；rules/service.py、l3_intents.py；diagnose/synthesize.py、decision.py；sessions/graph.py（route_entry、_diagnose_outcome）、l3.py（propose、advance_tasks）；escalation/summary.py；official/message.py；evaluation/live_tickets.py | common.py（HandoffBusiness）；data/eval/tickets/cases.yaml | SummaryCard.tsx 显示 business 字段 |
| 2 | official/qa_index.py；plans/models.py、qa.py；guide/steps.py、verify.py；sessions/router.py、graph.py（await_input、apply_action）、snapshot.py | common.py、actions.py、events.py、snapshot.py；data/official/qa_overrides.yaml | StepCard.tsx、Timeline.tsx、reducer.ts、Composer.tsx |
| 3 | conversation/answers.py、tasks.py、interpret.py（parts_purchase）、reply.py；prompts/reply.py；sessions/streaming.py | — | 消息失败状态与重试 |

## 7. 待决策

- D1 过保后是否继续自助排障（2.5）。默认继续。
- D2 事实问句卡的形态：选项加短答（默认），还是只自由文本。影响第二批契约。
- D3 是否新增 `parts_purchase` 意图并一律人工交接。默认是。
- D4 先提交今日未提交的两轮改动再开工。默认是，需用户授权提交。

## 8. 可选复杂度（本轮不做）

- 通用流程编排器、Q&A 可视化编辑。
- 875 条知识逐条产品专家复核。
- 用模型做步骤类型分类；规则加覆写文件已够高频条目。
