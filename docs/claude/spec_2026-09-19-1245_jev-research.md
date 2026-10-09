# Jev / jev-ultrafast 调研：对本框架的启发与改进点

调研对象：

- browser-use/jev-ultrafast（https://github.com/browser-use/jev-ultrafast）
- Sydney Runkle（LangChain）推文 https://x.com/sydneyrunkle/status/2100754364545761643 → 文章「Building a Harness with Jev」（https://www.langchain.com/blog/building-a-harness-with-jev）
- TypeSafe 官方文档：docs.typesafe.ai（system-one / models / model-jaggedness）

术语：

- **System One 模型**：只做「有界决策」的模型。输入 state（文本 / JSON）+ 若干 typed question，输出带概率的决策，不生成文本。
- **Choice / Score / Noul**：Jev 的三种问题原语。Choice 从候选里选一个并给全体候选的概率分布；Score 按有序等级打分；Noul 是 0–1 的是非概率。
- **speculative fan-out**：一次请求里放多个独立问题，模型对同一 state 并行作答；多问一个问题几乎不增加延迟，只增加该问题的 token。

## 1. Jev 是什么（事实）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 端点 | `POST https://api.typesafe.ai/v1/systemone`，model `jev-latest`（= jev-1.13.0） | docs/models |
| 输入 | 仅文本（string / JSON / 文本数组），不收图片 | docs/system-one |
| 上限 | 总上下文 64k；state + 最长问题 ≤ 32k；Choice 候选 ≤ 255 | docs/models、developersdigest |
| 延迟 | 官方 70–500 ms，多数约 100 ms | typesafe blog |
| 价格 | 输入 $0.042 / MTok，输出免费 | docs/models |
| 训练 | RLCD（对结果校准的强化学习），声称概率在总体上校准，单条不保证 | typesafe blog |
| 可用性 | 2026-09-15 起早期访问，需排队拿 key | typesafe blog |
| 语言 | 英文为主；CJK「支持但准确率下降，上线前须用自己的数据测」 | docs/models |
| SDK | Python / JS；LangChain 侧 `langchain-typesafe` 0.0.1a2（alpha）：`TypeSafeClassifier`、实验性 `AutoModeMiddleware`、`ModelRouterMiddleware` | PyPI、langchain PR #40556 |

官方列出的弱项（docs/model-jaggedness/jev-1.13）：字面理解、不擅长否定与多层间接指代；不会数数、不会比日期；state 里的无关信息会当干扰；不抗提示注入；P(yes) 与 1−P(no) 不保证一致。这几条与我们 intake 提示里的大量细则（「没有冒烟不是冒烟事实」「做过了没效果不算反馈」）直接冲突，见 §4 风险。

## 2. jev-ultrafast 的做法（事实）

浏览器 agent，每步一个循环：

```
DOM 快照 → 元素编号表（index 1..N，每个元素允许的操作）
       → 一次 Jev 请求，fan-out 问题：
            operation ∈ {CLICK, TYPE_TEXT, SELECT, SCROLL_*, WAIT, DONE, BLOCKED}
            click_target / type_text_target / select_target（每个操作一个独立 head，候选 = 该操作合法的元素编号）
       → validate_choice：choice 在候选集内、概率键集合 == 候选集、和 ≈ 1、argmax == choice，否则拒绝执行
       → 仅当 operation == TYPE_TEXT 才调小 LLM（默认 deepseek-chat，关思考），输出必须是 {"text": "..."} 单键 JSON
       → 执行前校验页面 fingerprint 未变；变了整步作废，不重试写操作
```

设计原则（AGENTS.md）：模型永远不输出选择器、坐标、代码；文本模型的输出先解析再用；写操作绝不重试；DONE 要独立验证。

性能（docs/performance.md，作者自报）：Google Flights 任务 7.1 s；与旧版对照 3 对交替运行，中位 9.45 s → 7.09 s（−25%），浏览器协议调用 1092 → 101。作者自己说明 3 对样本 p = 0.25，不构成统计结论；25% 的提升主要来自快照与协议调用优化，不是 Jev 本身。文本助手成本 $0.00006 / 任务，不含 Jev 费用。

LangChain 文章的三个用法：模型路由（先用 Jev 判断请求复杂度再选模型）、Auto mode 护栏（工具调用执行前先由 Jev 分类风险）、评估（用 Jev 对 agent 决策批量打分）。

## 3. 与本框架逐点对照

本框架一轮的串行链（graph.py `understand → … → reply`）：

```
rules.check_in（R3/R4 关键词，0 ms）
→ interpret_turn（task=intake，TurnInterpretation ≈ 30 字段，INSTRUCTION 3947 字，24 种 intent，≤60 个症状码候选）
→ disambiguate（目录匹配 + 三档判定，确定性；必要时 disambiguate.clarify 生成追问）
→ vision（可选）
→ retrieve（WeKnora）→ retrieve.grade（可选，逐条 relevant/irrelevant/unsure + coverage）
→ synthesize（从 allowed plan_id 枚举里选 ≤5 个假设，带 confidence 与 evidence_ids）
→ guide.step（生成步骤文案）→ reply.stream（生成回复）
```

设计文档 07 §16 记的最坏串行深度 4，约 15 s；实测（reports/eval/*-model.json，qwen3.7-flash）仅 interpret 一次：

| 评测 | n | p50 | p90 | 准确率 |
| --- | --- | --- | --- | --- |
| intent | 40 | 2094 ms | 2474 ms | 100% |
| routing（多意图排序） | 20 | 1909 ms | 3052 ms | 100% |
| emotion | 40 | 2273 ms | 3365 ms | 95%（2 例 calm → dissatisfied） |

对照结论：**本框架里「本质是选择题、却由生成式 LLM 用 JSON 答」的环节有六处**，它们正是 Jev 的形状；另有四处已经是确定性代码，与 jev-ultrafast「代码持有状态机，模型只做选择」的原则一致，不该动。

### 3.1 Jev 形状的环节

| 环节 | 现状（文件） | Jev 对应 | 备注 |
| --- | --- | --- | --- |
| 意图 / 情绪 / 症状码 / 反馈 / 安全断言 | `conversation/interpret.py` 一次 intake 调用混合输出 | primary_intent = Choice(24)；emotion_level = Score（calm<anxious<dissatisfied<angry<complaint_risk 是有序等级）；symptom_code = Choice(≤60)；feedback = Choice(3)；device_safety_assertion = Choice(4)；symptom_answer = Choice | 但 quote / facts.value / clarification 是文本抽取，Jev 做不了 |
| 计划排序 | `diagnose/synthesize.py` `PlansRanked`，模型自报 confidence，`filter_hypotheses` 丢越界 plan_id | Choice(allowed plan_ids) 直接返回全体候选的概率分布 | 概率分布比自报 confidence 可比较；越界不可能发生。evidence_ids 归因需另问 Noul(plan × evidence) 或保留 LLM |
| 证据评分 | `diagnose/grade.py` 每条 hit 一个 verdict + 总 coverage | fan-out：N 条 hit = N 个 Choice(3) + 1 个 Choice(coverage)，一次请求 | 目前 query.rewrite 三家都 62–75% 未达标、默认关闭；这是最低风险的替换点 |
| 情绪等级 | intake 输出 level，`emotion/policy.py` 规则映射策略 | Score + 概率 → 低置信时保守取 calm | 现有 2/40 误判就是边界样本 |
| 是否需要检索 / 二轮检索 / 读图 | 固定流程 | Noul「本轮需要检索吗」即 LangChain 的 ModelRouterMiddleware 用法 | 收益：省掉一次 200 ms 检索或 1–5 s 读图；先测是否值得 |
| 业务动作前置护栏 | `actions/gate.py` 规则 | AutoModeMiddleware：退款 / 换货 / 改地址执行前 Noul「用户是否明确要求」 | 现在靠 intake 的 quote 校验，已经够用；可作第二意见 |

### 3.2 已经是确定性代码、与 Jev 原则一致、不动的环节

- 产品确认三档判定（`sessions/clarify.py`，spec 2026-09-19-0810）：「模型猜测只能排序不能决策」。
- 症状问诊状态机 `taxonomy.next_interview` / `select_discriminator`：由词表切分选题，不问模型。
- 保修政策 `policy/engine.py`：纯规则。
- 情绪 → 策略映射 `config/emotion_policy.yaml`：规则表。

### 3.3 jev-ultrafast 的工程约束在本框架里的对应

| jev-ultrafast | 本框架 | 差距 |
| --- | --- | --- |
| `validate_choice` 严格校验概率分布 | `filter_hypotheses`、`normalize_result` 白名单过滤 | 我们只校验「在集合内」，没有分布约束；自报 confidence 无校准 |
| 页面 fingerprint 变了整步作废 | checkpoint `base_version` + 取消路径 | 等价 |
| 连续 3 步无变化 → BLOCKED | `MAX_NO_PROGRESS=2`、`MAX_INTERVIEW_RESPONSES=8`、R7 | 等价 |
| recent_actions 最近 10 条进 state | history 全量进 context，按预算裁 | 我们更重 |
| 文本模型输出必须是单键 JSON 否则不打字 | Pydantic + `quote in text` 校验 | 等价 |
| performance.md 公布对照对数、协议调用数、token、成本、p 值 | run 有 first_visible_ms / card_ready_ms，analytics 有 model_call 表 | 缺「每轮 LLM 调用次数 / 串行深度 / LLM 总耗时」这三个汇总指标，无法回答「一轮里模型占了多少」 |

## 4. 不用 Jev 也能立刻做的改进（设计层面的收获）

这部分与是否拿到 Jev key 无关，收益来自「把决策和写作分开」这个思路。

1. **intake 拆成「决策头」和「抽取头」**。现在一次调用输出约 30 个字段、3947 字提示，p50 2.1 s；其中约一半字段是有界选择，另一半是逐字引用。拆法：先跑一个小 schema（intents、emotion_level、feedback、device_safety_assertion、symptom_answer、是否含新事实）；只有 report_problem / supplement / correct / 业务意图才跑第二个抽取 schema。小模型的延迟由输出 token 主导，小 schema 直接缩短首字时间；两头可以并行发出，串行深度不增加。代价：两次调用的 token 总量略高于一次。
2. **把「逐字引用」改成「片段编号」**。把用户本轮文本按标点切成带编号的片段放进 state，让模型选片段编号而不是复述原文。这一步把 quote 从生成问题变成选择问题：`interview_answer` 里 `answer.quote not in text` 的失败路径消失，也为以后接 Jev 铺路。适用：facts.quote、feedback_quote、human_request_quote、emotion_cues。
3. **合并 grade 与 synthesize 为一次 fan-out**。两者读同一批证据，现在串行两次（1–2 s）。同一请求里同时问「每条证据相关吗」和「计划排序」，代码再用 verdict 剪枝排序结果。可选复杂度：只在 grade 开启时合并。
4. **要分布不要自报置信度**。synthesize 让模型给出对全体 allowed plan 的概率并校验和 ≈ 1、argmax 一致，否则降级到 `default_plans_ranked`。低置信（top1 − top2 < 阈值）作为一等分支进 clarify，而不是硬选。
5. **补三个每轮指标**：`model_calls`、`serial_llm_depth`、`llm_ms_sum`，写进 run 事实并上观测台。07 §16 的原则是「减少一次 LLM 调用的收益大于任何数据库优化」，但现在没有指标能证明某次改动减少了调用。

## 5. 若接入 Jev：分阶段方案

前提：拿到 key；且第 0 阶段在中文数据上达标。Jev 不是 chat model，接不进 `ModelRouter` 的 `BaseChatModel` 路径，需要单独的决策通道。

| 阶段 | 做什么 | 门槛 |
| --- | --- | --- |
| 0 离线 | 用现有金标 `data/eval/{intent,routing,emotion}/semantic-gold.yaml`（40/20/40）+ 症状回归 40 条，直接调 `/v1/systemone` 跑 Choice / Score，与 qwen3.7-flash 的 100/100/95% 对比 | 中文准确率不低于现值；p50 < 500 ms。不达标即止 |
| 1 影子 | `interpret_turn` 里并行发 Jev，结果只写 `model_call` / trace，不影响行为；看一致率与分歧样本 | 一致率与人工复核 |
| 2 替换有界头 | 顺序：retrieve.grade → synthesize 排序 → emotion_level；LLM 保留为降级链尾（models.yaml 新增 task kind `decision`，chain `[jev, <现 LLM>]`） | 每步走 bakeoff |
| 3 拆 intake | §4.1 + §4.2 落地后，决策头换 Jev，抽取头仍 LLM | 同上 |

实现要点：

- 接入方式二选一：`langchain-typesafe`（alpha，随 langchain ≥ 1.0）或仿 jev-ultrafast `model.py` 直接 httpx（约 100 行，含 `validate_choice`）。后者依赖少、可控，建议先用后者。
- 单测：仿 `app/models/fake.py` 加 `FakeDecisionModel`，`HAIKE_LLM=off` 时决策头也走 fake。
- Jev 属海外通道：客户文本出境的合规判断与 overseas lane 相同，默认 domestic lane 不启用。

## 6. 风险与不采用的理由

- **中文准确率未知**，官方明说 CJK 下降。我们全部输入是中文口语，第 0 阶段必须先跑。
- **否定与间接指代是 Jev 弱项**，而 intake 提示里的大量细则就是在处理这些（「没有冒烟」「做过了没效果」「这笔订单」）。这些必须留在代码（`_mask_negated` 已有）或留给 LLM，不能指望 Jev 读懂。
- **拿不到 key** 时全部停在 §4。
- jev-ultrafast 的 25% 提速样本量 3 对、p = 0.25，且主要来自运行时优化；不要把它当作「换 Jev 就快 25%」的依据。
- 它默认文本模型是 deepseek-chat 关思考，与我们 models.yaml 的 `thinking: {type: disabled}` 选择一致，算旁证不算收益。

## 7. 结论

- Jev 对本框架的价值不在替换整条链，而在六个「本质是选择题」的环节；其中 grade 与 synthesize 排序风险最低、intake 拆分收益最大。
- 与 Jev 无关、现在就能做的四件事：intake 决策 / 抽取分头、引用改片段编号、grade + synthesize 合并 fan-out、补每轮 LLM 调用指标。
- 接入 Jev 的硬门槛是中文离线评测，金标与评测器（`evaluation/semantic.py`）已经现成。
