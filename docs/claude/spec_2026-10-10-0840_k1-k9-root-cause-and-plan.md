# 十轮残留案例的根因与处理方案（K1–K9）

来源：`docs/planning/2026-10-09-1938_ten-round-improvement/next-phase-design.md` 与 round-08 / round-10 轨迹、checkpoint，代码为 `codex/official-63-ten-rounds` 工作区版本。

## 0. 一句话根因

五类残留问题共用一个结构性缺陷：**服务端只校验「来源」（模型引的原话确实在文本里、id 确实在列表里），不校验「语义」（这句话是不是危险、这个前提是否成立、这个问题是否已经被回答）。** 语义判断被整体委托给模型自评，服务端没有可比对的结构化数据，于是模型一错就直接变成升级、发卡、追问或统计口径错误。

修法也只有一个模式：**模型只负责抽取与建议，输出必须落到封闭词表或结构化字段；服务端拿这些字段与已知事实做确定性比对；比不出来就问一个针对性问题，不能凭模型标签直接执行高后果动作。**

## 1. 逐案例追踪

### T23：E41 电池报码被当成物理安全事件（K8）

原文只有设备推送 `E41: Battery abnormal, task ended. Please try restarting or contact customer service`。

追踪：

- 词表预检 `config/rules/safety_terms.yaml` 没有命中 R4，checkpoint `safety_flags` 只有 R3（`contact customer service`）。
- `reduce.py:381` 的 `new_risk = device_safety_assertion == "reported" and quoted(quote, text)`。`quoted()` 只看原话是否在文本里。模型把 `Battery abnormal` 标成 reported，原话确实存在，于是直接建 R4、`no_operations`、入人工。
- 对比 R3：同一文件已经用 `quote_source()` 区分「设备推送」和「用户陈述」，设备文案里的 contact customer service 不算用户要人工。R4 没有做同样的区分，也没有危险类别校验。

根因：安全主张有三个独立属性，来源（谁说的）、语义（什么危险）、语气（肯定 / 否定 / 转述）。现在只校验来源。

### T41：未拖地却命中「拖完不够干」rv-0146（K1 / K2）

原文：收到 failed drying 报错，但注水故障导致「we have not run mop cycles」，不知道什么触发。

追踪：

- rv-0146 的内容是「升级固件后执行一次新的拖地任务确认是否解决」，隐含前提是「跑过拖地、烘干了、结果仍潮」。这个前提在条目里是自然语言，索引里没有字段。
- `filter_hypotheses` 的确定性检查只有四种：polarity_uncertain、timing_mismatch、subject_mismatch、code_mismatch。用户事实「没跑拖地」是一个否定的事件，不属于这四类，于是落到 `applicability` 自评。第八轮模型自评 supported，发了卡。
- 第十轮模型改说 needs_confirmation，`clarification_question` 是自由文本「Does the error appear even when no mop cycle has been run?」。这句话用户已经答过，但服务端没有拿问题和已有事实比对，照样发问。

根因：知识条目的「适用条件」没有数据表示，运行时无法和事实比；追问也是自由文本，无法判定是否已被回答。两者是同一个缺口的两面。

### T53：已说无法开机，仍让在「无法开机 / 加热故障」里二选一（K7）

追踪：

- 事实里有 `symptom: stoped turning on`。bp-0114 有两个故障小节，`plans/qa.py:62` 只要 `guide.sections` 存在就无条件发 `select_scope` 问句卡。
- `guide/steps.py` 的 `prepare_step` 对 question 类型没有「先查事实再问」的分支，分支只能由用户点选消费。

根因：问句被当成固定步骤发布，不是当成「缺一条信息」来求值。

### T35：产品咨询已答却统计 in_progress；回复里出现拼接的假 UUID（K9 / K7）

统计部分：

- `product_questions.py:177` 只写 `task["status"] = "answered"`。`graph.py:1180` 把 `turn_decision.product_answered` 置真后路由到 disambiguate，但 `consult_answered` 这个 checkpoint 字段只在 `l3.advance_tasks` 与 guide 的 explained 路径写。
- `analytics/derive.py:classify` 按优先级读 `case_status → stage → consult_answered → ...`，看不到 `product_question.status`，于是 in_progress。

引用部分：

- `knowledge/context.py:evidence_header` 把证据渲染成 `[<36 位 uuid>] (kb_qa) 标题…` 交给模型；产品咨询的提示词没有像 `prompts/reply.py` 那样要求「用 [1] [2] 编号且正文不得出现」。
- 模型抄写 UUID 时把 `05af0178-096c-43b6-…` 和 `38e656c1-…-47d0-b317-fc99b221f68e` 拼成了一个不存在的 id，原样流式输出。服务端 `citations.attribute` 其实用句子重叠算出了正确引用，但正文已经发给用户。

根因：完成状态分散在 task.status / consult_answered / stage / case_status 四处，各入口各写各的，派生函数按优先级猜；模型被允许输出标识符。

### T53 结案口径：换货案件 closed_unresolved，维修任务还 active（K9）

`classify` 第一条就是 `case_status == closed_unresolved → closed_unresolved`，不看 task_queue。多诉求下案件终点覆盖了整个问题终点。

### T27 / T31 / T37：复合卡局部重复（K5）

`matches_reported` 要求一张卡的全部动作、全部部件都被用户报告覆盖才跳过，否则整卡重发。这是刻意保守（T29 曾因 cleaned 跳掉密封检查）。真正的修法依赖把复合卡拆到动作粒度，与 K1 同一套编译。

## 2. 方案

### 原则

1. 模型输出落封闭词表或结构化字段，不输出标识符、不输出自由文本的判定依据。
2. 服务端拿字段与事实做确定性比对：成立 / 不成立 / 未知。
3. 未知且会改变下一步才问，问题由缺失字段生成，不由模型自由写。
4. 高后果动作（升级、禁操作、结案）不接受「模型标签 + 原话存在」作为充分条件。

### 阶段 A：确定性门槛（小改动，先做）

A1 安全主张结构化（T23）

- `interpret.py` 的 `device_safety_assertion/quote` 改为 `DeviceSafetyClaim {hazard: smoke|burning_smell|fire|swelling|leak|shock|overheat|melt|none, quote, polarity, subject}`。
- `reduce.py`：立即建 R4 需要同时满足 hazard ≠ none、`quote_source(quote) == "user_statement"`（设备推送除非推送文本本身含 R4 词）、quote 命中该 hazard 对应的词表。模型 reported 但词表不支持 → 不升级，发一条封闭式安全澄清（是否有冒烟 / 异味 / 鼓包 / 发烫 / 漏液），澄清期间保留 `pre_step` 高风险动作限制，允许 app 内固件更新这类非接触步骤。否定后正常排障。
- 词表命中但模型 none 的情况维持现状（宁可误报）。
- 验收：真实冒烟、E41 普通报码、「没有冒烟」否定、转述手册警告、历史危险后更正。不为 E41 加豁免。

A2 引用不经模型之手（T35 / T48）

- `product_questions.py` 改用与 `prompts/reply.py` 一致的 `[1]..[n]` 编号渲染，提示词加「正文不得出现编号或 id」。
- `streaming.py` 流式输出加一层过滤：缓冲 `[` 开头片段，`[` + uuid 形状的 token 直接丢弃。
- 引用展示只用 `message_end.citations`（服务端 `attribute` 算出来的真 id）映射到文档标题 / 条目号。

A3 问句先查事实再发（T53）

- `synthesize.py` 的 Hypothesis 增加 `matched_section`（摘自候选原文的小节标题）。服务端校验必须逐字等于 plan 的某个 section title，且 `supported_symptoms` 非空；通过则 `plan_cursor` 直接落到该小节首步，`answered_history` 记一条 `source=fact` 的自动回答。
- 校验不过仍发 `select_scope`。不加「turn on ≈ cannot be turned on」之类同义词表。

A4 追问不得重复已知事实（T41 第十轮）

- 临时门槛：模型的 `clarification_question` 必须附 `missing_fact`（它想确认的前提原话，摘自候选正文）。服务端用现有 `_subject_conflicts` 同族逻辑比 `missing_fact` 与 active facts（含 negated），已有事实覆盖则不问，按事实极性直接判 not_applicable 或 supported。
- 这是阶段 B 落地前的过渡，B 完成后 `missing_fact` 由编译结果提供而不是模型。

### 阶段 B：知识条目的适用条件编译（K1 / K2，中等）

现状规模：875 条 Q&A，1829 个步骤（action 1438、statement 301、handoff 72、material 12、question 6），410 条多步，只有 bp-0114 一条有互斥故障小节。

- 新增生成文件 `data/official/qa_compiled.yaml`，按 `qa.yaml` 的 sha 版本化，由 `python -m app.official.compile` 一次性生成：每条记录 `phenomenon`（现象，来自标题）、`preconditions[]`（必要前提，形如 `{text, event: mop_cycle_ran|charging|after_firmware_update|…, polarity}`，摘自正文原话并带字符区间）、每个步骤的 `atomic_actions[]`（动作 + 对象，供 K5）。
- 模型只做抽取，输出必须引用正文区间；人工抽查两个品类各 30 条，错的写进 `qa_overrides.yaml`。
- 运行时 `filter_hypotheses` 增加 `precondition_mismatch`：事实中有同事件的 negated 项 → not_applicable；没有任何事实 → needs_confirmation，问题由 precondition.text 生成；用户回答写回 facts。
- K4：`knowledge_status` 区分 `not_recalled / recalled_not_applicable / source_incomplete / model_unavailable`，回复模板按此四种措辞。
- K5 跟着这一步：`matches_reported` 从整卡改为逐 atomic_action 比对，已做的动作在卡上标记，未做的保留。T29 的保护仍成立，因为密封检查是独立 atomic_action。

### 阶段 C：统一完成契约（K9，中等）

- 新建 `app/analytics/outcome.py`，一个纯函数 `derive_outcome(tasks, case, pending_card, clarification, done_reason)`，定义唯一的聚合规则：任一任务 active/pending 且无 pending 用户输入 → in_progress；全部任务终结再看案件；案件 closed_unresolved 但仍有 active 排障任务 → in_progress 并带 `partial_closed` 原因。
- 产品咨询不再用旁路 `product_question` 字典，进 `task_queue`，status 取 `answered | insufficient_evidence | unanswered`；流式完成不等于 answered，`result.completed` 且 `citations` 非空才 answered。
- checkpoint 写入 `outcome` 字段；`classify`、episode、`METRIC_ROWS_SQL`、`l3.py` 全部改读该字段，删掉各自的 if 链。

### 不做的事

- 不按工单或 QA 编号加生产分支；不为 E41、bp-0114 单独写规则。
- 不降低 R4 保护换成功率；模型未确认且词表命中仍升级。
- 不做知识编辑器、自动回滚（可选复杂度，留后）。
- T50 措辞、T57 术语歧义是资料内容问题，走 `official-source-review.md` 人工核对。

## 3. 顺序与验收

| 阶段 | 预计 | 覆盖案例 | 验收 |
| --- | --- | --- | --- |
| A | 1 天 | T23、T35、T48、T53 分支、T41 第十轮重复追问 | Fake 模型正反例各 ≥3；63 单复测 T23 不再 R4，T53 直落无法开机小节，T35 正文无 id |
| B | 2–3 天 | T41 第八轮、T27/T31/T37、K4 文案 | 两品类合成前提正反例；留出 10 单未参与开发的工单 |
| C | 1–2 天 | T35 / T53 统计 | 真实 Postgres 四种投影；多案件 + 咨询 + 排障混合会话 |

A 与 C 互不依赖，可并行；B 之后再回收 A4 的过渡逻辑。

工作区当前是 `codex/official-63-ten-rounds` 的未提交改动（46 个文件），本方案建立在这些改动之上；开工前先决定是否先提交 Codex 的十轮代码。
