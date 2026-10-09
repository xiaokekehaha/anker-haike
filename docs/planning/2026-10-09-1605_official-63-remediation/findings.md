# 代码核对事实（2026-10-09 16:05）

对照测评文档 `docs/codex/2026-10-09_官方63案例全量测评与改进判断.md` 的 I1–I9，逐条核对首测轨迹（`../2026-10-09-1515_full-official-evaluation/T*.json`）与当前工作树代码。行号为当前工作树（含今日未提交改动）。

## I1 T11：设备提示被当成主动转人工

- 轨迹：`understand` 一步就 `primary_intent=request_human`、`rule=R3`，路径 understand → escalate → summarize；摘要 reason 写「命中词：contact customer service」。
- 代码：`conversation/reduce.py:382-387` 只校验 `human_request_quote` 是否逐字出现在原文，不校验这句话是谁说的。原文里 `Click to contact customer service for assistance` 出现在 `Problem Push` 与 `Problem Description` 字段，`official/message.py:93-121` 的 `parse_message` 已能分出这两个字段，但解释与归约环节没有用它判定来源。
- `config/rules/safety_terms.yaml:19` R3 词表含 `contact customer service`；`rules.check_in` 的 R3 命中只在模型失败的兜底解释（`l3_intents.py:45-60`）里设意图，正常路径不设。所以 T11 主要是模型判意图 + 归约只查引文存在性。

## I2 T18/T22/T30/T31/T34：已知错误码/症状未稳定进入适用方案

- T18：检索证据含 rv-0147（3212 正解）与 rv-0148，synthesize 却输出 `needs_confirmation` 并追问「3212 还是 3202」。错误码 `3212` 已由 `parse_message().codes` 解析出来，但 `diagnose/synthesize.py:142-200` 的提示只给 `symptoms/observations/current_turn`，不给已解析的错误码；`exact_code_hits`（`graph.py:1511`）命中后仍要过模型适用性门槛。
- T22/T30：`knowledge_status=ok`，证据列表含正解文档（T30 含 rv-0443），最终 `escalate_reason=R5`。即全部假设被 `filter_hypotheses`（`synthesize.py:84-125`）以 `not_supported` / `no_supported_symptom` 丢弃。该门槛是今日未提交改动（round5 routing fix）加入的，测评镜像包含它。复测能进入方案，说明是模型判 applicability 的波动，不是知识缺失。
- T31：没有进检索。路径 understand → reassess → R2。原因：模型把「despite wiping clean the electrical connections」解释成 `operation_update`，`reduce.py:300-302` 置 `operation_changed`，`graph.py:1397-1398` 路由到 `reassess`，`decide_next`（`decision.py:270`）在没有任何 `plans_ranked` 时直接 `knowledge_coverage_missing` → R2。首轮没排障就进 reassess 是路由漏洞。
- T34：`knowledge_status=ok` 仍 R5，同 T22 机制；摘要 problem 写「尚未记录具体故障现象」。

## I3 T50/T52/T61：事实对象、极性、方向被改写

- 事实模型 `FactCandidate`（`interpret.py:55-63`）只有 kind/value/quote/时间，没有部件、极性（肯定/否定）、方向（提前/未发生）、确定性。只有安全有 `device_safety_assertion` 极性字段。
- T50：issue 标题就是「left one does work」，synthesize 把 bp-0020「左右马达表现不同」判为 supported，首步即操作卡，无澄清。
- T52：标题「charging case will not charge」，选中 bp-0067「泵在盒子里充不上电」，对象链（电源→盒子 / 盒子→泵）未区分。金标 bp-0039/0127/0067 三条全是「盒子给泵充电」。
- T61：`described()`（`decision.py:47-63`）靠「≥6 词」兜底放行，没有抽出结构化现象；synthesize 以 rv-0522（7051 无法启动）发 needs_confirmation 问「是否 7051」。今日提示词已写「区分方向、时间」，但没有结构化字段可核对。

## I4 T46 等：文档段落统一成操作卡

- `official/qa_index.py:53,129-187`：按 `STEP_LINE` 编号拆段，`Guide.kind` 只有 steps/answer/warranty；`Step` 无类型字段。bp-0123 原文「Step 1: Identify the Problem / 1. Is the noise continuous or intermittent? / 4. Please record a short video」全部被编号成步骤。
- `plans/models.py:24` `PlanStep` 无 kind；`plans/qa.py:52` 给每段同样的 `EXPECTED` 与 solved/not_solved/cannot_do 三条边。
- 契约 `contracts/haike_contracts/common.py:103` `TroubleshootStep`、`actions.py:70` `StepFeedbackAction` 只支持三种反馈；前端 `StepCard.tsx` 固定三按钮。澄清问句（`sessions/clarify.py:31`）以纯文本发出，没有选项卡。
- `guide/verify.py:94` 对 not_solved 一律 `executed+1`，标题/说明/问句也计入已操作。

## I5 T27/T36/T37：用户已做的排查没有利用

- `FactCandidate.kind` 无 action_taken；`step_attempts` 只记卡片反馈（`operation_conditions.py:67-74`）。synthesize 与 `prepare_step` 都不知道用户自述已做过什么。T31 把「已擦过触点」解释成 operation_update 也是同一缺口的副作用。

## I6 T51/T53：过保结束整个会话

- `sessions/l3.py:335-345` 过保分支硬编码 `{"stage": "done", "l3_route": "commit_issue"}`，不走 `finish()`（`l3.py:127-129`）也不走 `advance_tasks`。T51 轨迹 task_queue 里 `report_problem` 仍 `pending`，而回复已说「I'll handle your requests in this order: replacement → troubleshooting」。

## I7 T22/T34/T58/T60/T63：信息不足就交接、摘要丢要点

- T60：无 symptom 事实（标题「待描述的问题」），`described()` 按词数放行 → 检索 no_match → R5 直接入队。`_diagnose_outcome`（`graph.py:2231`）在 no_match 且无结构化现象时没有先澄清。
- 摘要 problem 字段只取 active symptom facts（`escalation/summary.py:192`），事实未抽出时写「尚未记录具体故障现象」，不回退到 `parse_message().push/description` 或 issue 标题。
- T22「NL 记成购买渠道」：`official/message.py:LABELS["country"]` 把 `Inlogland` / `Land van accountregistratie` 一并当 country，`summary.first_message_facts`（`summary.py:217-233`）渲染为「客户自述购买渠道」。
- 交接摘要无按业务类型的字段（订单暂停 / 设备故障 / 配件采购），只有 rule_id + reason 文案（`summary.py:124-214`）；T9 的摘要在物流查询前生成，`summary_refresh` 存在但 advance_tasks 完成后未触发。

## I8 T9/T47/T63

- T9：`order_change` 任务 waiting_human、`logistics_query` done，案件真实入队；只差摘要内容。
- T47：`answers.render_answer`（`answers.py:95-117`）只渲染订单包裹字段，不比对客户问的 SKU 与订单商品。
- T63：无「配件购买」意图（`interpret.py:25-50` Intent 枚举），该诉求没有任务也进不了摘要。

## I9 T35

- `prompts/reply.py:47-49` 把证据标成 `[8位id] snippet` 交给模型，`REPLY_INSTRUCTION` 未禁止回显；无后处理去除。
- `conversation/reply.py:224-235` 流式失败只捕获 `ContextBudgetExceeded`；`completed=False` 时用同一 `message_id` 追加固定兜底文案，用户看到的是一条「完整」消息；`last_error` 不记录。

## 评测标签

- `data/eval/tickets/cases.yaml:76,78,87,72`：T50 note 直接按 doesn't work 读、sop=troubleshoot；T52 qa_gold 三条都是盒子→泵方向；T61 qa_gold 为无法启动条目；T46 qa_gold 含吸力条目。`evaluation/live_tickets.py:284` 驱动器对所有卡一律 not_solved，不会在事实问句卡停下；`sop_passed` 只看终点，不查 stage=done 时的 pending 任务。
