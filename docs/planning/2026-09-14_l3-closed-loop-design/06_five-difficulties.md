# 第六步：五个难点的深化设计

每节按「现状 → 目标 → 设计 → 评测口径」。全部通过票 51 的契约扩展落地字段，不再另改 Literal。

## 1. 看图：从观察到故障定位（D-L3-11）

**现状**：`diagnose.vision` 输出 `observations[]` + `visible_parts[]`（[vision.py](../../../orchestrator/app/diagnose/vision.py)），失败按文字继续，无质量判定。

**目标**：图片 → 结构化定位直接命中计划；不可用图触发补拍；图文冲突先澄清。

**设计**
```python
class Finding(Strict):
    part: str                      # 受控词表：滚刷/边刷/滤网/尘盒/吸口/轮组/传感器/充电触点/电池仓/基站/其他
    location: str | None           # 左端/右端/中部/底部/顶部/接口处…
    phenomenon: str                # 受控词表：缠绕/堵塞/破损/变形/烧焦/漏液/鼓包/污渍/松脱/缺失/正常
    severity: Literal["low","medium","high"]
    confidence: float
    quote_region: str | None       # 「左下角」类粗略区域，供人工核对
class ImageQuality(Strict):
    usable: bool
    reasons: list[Literal["blurry","too_dark","too_far","wrong_subject","occluded"]]
class FaultLocalization(Strict):
    findings: list[Finding]
    image_quality: ImageQuality
    model_hint: str | None         # 铭牌/机身可读到的型号文字（只抄写不猜）
    conflicts_with_text: list[str] # 与用户文字明显矛盾的点
```
- 任务仍为 `diagnose.vision`，prompt 版本升 `2026-09-14.1`；受控词表放 `config/vision_vocab.yaml`，输出不在词表 → 归「其他」并保留原文到 `raw`。
- 向后兼容：`observations = [f"{part}{phenomenon}" ...]` 派生，安全 `observation_terms` 匹配继续走 CP-in（增加中文词到 `observation_terms`）。
- 命中计划：`fault_card_hits` 增加按 `(part, phenomenon)` 的确定性映射（`config/fault_cards.yaml` 的 faults 增加 `signatures: [{part, phenomenon}]`），命中即提高该 plan 的先验，synthesize 仍需引用证据。
- `model_hint` 进入 disambiguate 候选（读到「X10 Pro」直接单命中，省一轮追问）。
- `image_quality.usable=false` 且本 run 无其他可用图 → `prepare_retake → await_input`（RetakeCard：原因 + 拍摄指引，来自 `config/vision_vocab.yaml.retake_guidance[reason]`）；用户可跳过（`skip_retake`）→ 文字流程；补拍计入 clarification（reason=image），受 R7 上限。
- `conflicts_with_text` 非空 → `clarify`（reason=conflict）先问，不进检索。
- 视觉链失败 / 无视觉模型：行为不变（固定提示）。

**评测**：`data/eval/vision/cases.yaml`：≥ 20 张（真实故障图优先，缺则用公开图 + 自拍），金标 `findings[part, phenomenon, severity]`、`usable`；指标：part 命中率、phenomenon 命中率、usable 判定准确率、命中正确 plan 的比例。bake-off 对 deepseek / qwen-vl / glm-v / sonnet / gemini 重跑该 schema（新 schema 需重新达标）。

## 2. 问清：口语到故障类型

**现状**：intake symptoms + interpret facts；同义词表 11 组手写；`query.rewrite` 62–75%；计划命中靠 fault_card keywords。

**目标**：口语 / 主观 / 错别字描述稳定映射到故障类型；追问按信息增益选题。

**设计**
- **症状体系**：`config/symptom_taxonomy.yaml`：`fault_family`（吸力下降 / 不开机 / 不充电 / 异响 / 漏水 / 导航异常 / 拖地异常 / App 连接…）→ `symptom_code` → 表述集合（口语、错别字、方言式、否定式），每条带来源（工单 / 人工）。P0 只做扫地机 6–8 个族；结构为多品类预留 `category` 维度。
- **归一化**：interpret 的 `FactCandidate` 增加 `symptom_code: str | None`（模型从给定候选列表里选，不自由生成；候选列表按 category 注入 prompt，≤ 60 条）；规则侧用 taxonomy 表述做确定性回退匹配；两者不一致以规则为准并记 trace。
- **计划映射**：`fault_cards.faults[].symptom_codes` 替代自由 keywords 命中；keywords 保留为兼容。
- **追问选题**：`clarify` 增加确定性「区分力」计算：对候选 fault_family 集合，选能最多二分的问题（配置 `symptom_taxonomy.yaml.discriminators: [{question, splits: {yes:[family…], no:[family…]}}]`），仍受 R7 两次上限；问题措辞由 `disambiguate.clarify` 润色。
- **同义词表数据化**：`retrieval.yaml.synonyms` 由 taxonomy 生成（`haike-taxonomy export-synonyms`），不再手写两份。

**评测**：`data/eval/symptom/cases.yaml` ≥ 40 条口语（优先来自脱敏工单原话）→ 金标 fault_family / symptom_code；指标：族准确率、码准确率、无法归一（unknown）率；澄清评测：给定歧义输入，追问后两轮内命中族的比例。

## 3. 分流：多诉求与多区域（D-L3-12/13）

**现状**：`secondary_intents` 无消费者；无区域 / 渠道维度；14 意图无业务意图。

**设计**
- **意图扩展**（interpret.py）：`Intent += logistics_query | warranty_query | order_query | address_update | replacement_request | refund_request | confirm_received | rate`。`CONSULT_INTENTS = {logistics_query, warranty_query, order_query, address_update(P1)}`；`REMEDY_INTENTS = {replacement_request, refund_request}` 走 R6 路径进 propose。规则回退：`config/rules/intent_terms.yaml` 关键词表在模型不可用时给保守意图。
- **任务队列**：`understand` 后、路由前，`reduce_turn` 把 `secondary_intents` 中属于 CONSULT/REMEDY/report_problem 的项写入 `issue.task_queue`（去重、带 quote）。优先级：safety(R4) > request_human > REMEDY > report_problem/排障 > CONSULT > social。`reply` 在首条可见消息后追加一句「您提到的 X 我会在 Y 之后处理」（确定性模板）。当前任务到达终态（`close` / `execute` 完成 / `consult` 完成）时，`route_after_*` 检查队列 → 直接进入下一任务节点（同一 run 内继续），并发 `issue_changed`。
- **服务上下文**（`service_context` 节点，02 §2.1）：四字段 `region_purchase / region_use / channel / platform`；来源优先级：凭证事实（订单表 region_purchase/platform；名录 region）> 用户明确陈述（interpret facts kind=context）> ContextCard 选择；每字段记 `source`。政策引擎缺输入即追问，不猜。
- **路由多维**：`KnowledgeScope` 增加可选 `region: str | None`，知识条目 front-matter 增加 `region_list`（标量串）；检索过滤：区域专属文档只在区域匹配时召回，通用文档不受影响（P1 数据到位后启用；P0 只加字段）。

**评测**：`data/eval/routing/cases.yaml`：多意图拆分（≥ 20 条：主次意图 + 期望顺序）、区域 / 渠道触发（≥ 10 条：期望 needs_human 或 allow）；指标：主意图准确率、次意图召回、顺序正确率、needs_human 判定准确率。

## 4. 接稳：情绪分级与策略矩阵（D-L3-10）

**现状**：3 级 → 3 种 prompt 层；「投诉」关键词 R3 直升级；无轨迹。

**设计**
- **四级**：`EmotionLevel = calm | dissatisfied | angry | complaint_risk`。interpret 输出单轮 level + `emotion_cues[]`（原话引用）；`complaint_risk` 由模型或规则给出（词表：投诉 / 315 / 消协 / 曝光 / 差评 / 律师 / 退货退款不然…），规则命中优先。
- **轨迹**：`issue.emotion_track` 保留最近 6 轮 `{input_id, level}`；派生 `trend ∈ {stable, rising, falling}`、`unresolved_turns`（自上次进展以来的轮数）。
- **策略矩阵** `config/emotion_policy.yaml`：
```yaml
strategies:
  normal:                      {tone: direct,  pace: normal,  actions: []}
  reassure_first:              {tone: warm,    pace: normal,  actions: []}
  reassure_and_shorten:        {tone: warm,    pace: fast,    actions: [shorten_steps]}
  direct_resolution:           {tone: apologetic, pace: fast, actions: [skip_optional_clarify, prefer_proposal_over_more_steps]}
  de_escalate_and_offer_human: {tone: apologetic, pace: fast, actions: [offer_human, flag_complaint_risk, prefer_proposal_over_more_steps, suggest_compensation_review]}
rules:   # 自上而下首条命中
  - {when: {level: complaint_risk},                              strategy: de_escalate_and_offer_human}
  - {when: {level: angry, trend: rising},                        strategy: de_escalate_and_offer_human}
  - {when: {level: angry},                                       strategy: direct_resolution}
  - {when: {level: dissatisfied, unresolved_turns_gte: 3},       strategy: direct_resolution}
  - {when: {level: dissatisfied},                                strategy: reassure_and_shorten}
  - {when: {level: anxious_or_calm_with_risk},                   strategy: reassure_first}
  - {when: {},                                                   strategy: normal}
```
- **动作落点**：`shorten_steps` → guide prompt（已有）；`skip_optional_clarify` → clarify 只问必要项；`prefer_proposal_over_more_steps` → `route_after_guide` 在 executed ≥ 2 且 not_solved 时直接 R2 进 propose 而非再出步骤；`offer_human` → reply 末尾追加人工选项（确定性文案）且 `request_human` 不需再确认；`flag_complaint_risk` → case.complaint_risk=true、priority=high；`suggest_compensation_review` → 摘要 `recommended_options` 加「补偿评估（需人工）」项，不自动执行。
- 「投诉」从 R3 `text_terms` 移除，改由 complaint_risk 路径处理；「转人工 / 人工客服」等明确请求仍 R3。
- `compose_system_prompt` 的情绪层按 strategy.tone/pace 生成，文案模板配置化。

**评测**：`data/eval/emotion/cases.yaml` ≥ 40 条（含反讽、emoji、多轮升温），金标 level；策略评测：给定轨迹 → 期望 strategy；A8 回放断言。

## 5. 幻觉：把约束从排障域扩到办理域（D-L3-5）

**现状**：plan_id / evidence_id 白名单、步骤只改写原文、CP-pre-step、`<data>` 包裹、四态知识结果。

**设计（新增五道）**
1. **动作白名单**：只有 `config/actions.yaml` 注册的 kind 可执行；LLM 输出中不允许出现动作名（模型不参与决定「办什么」，只参与「怎么说」）。
2. **政策引用强制**：用户可见的任何资格 / 费用 / 时限表述必须来自 `PolicyDecision.clauses` 或 `Receipt` 字段的模板渲染；`propose.wording` 润色沿用 `escalation/polish.py` 的整句保持校验 + 禁词表（新增「一定 / 保证 / 肯定可以退 / 全额」等承诺词），失败直渲染模板。
3. **承诺账本**（P0 只记录，P1 用于补偿一致性）：`case.commitments[]`：每次用户可见的方案 / 时限 / 费用承诺落一条 `{text, source: clause|receipt, at}`；后续回复生成前把账本注入 `<data kind=commitments>`，并在 reply 后做确定性一致性检查（出现与账本冲突的金额 / 天数 → 丢弃该句用模板）。
4. **授权门审计**：每次 execute 的 gate checks / policy_version / actions_version 落库并进摘要；越权评测集在 CI 跑，越权 = 失败。
5. **诚实升级**：`consult` 找不到订单 / 后端不可用 → 固定文案 + 转人工选项，不用模型编状态；`propose` 无 eligible → 「按当前政策无法自动办理」+ 条款 + 人工。
- 多模型交叉审核：P2 评估，P0 不做（成本与延迟）；先用确定性检查覆盖。

**评测**：越权评测（03 §8）、承诺一致性评测（≥ 10 组多轮，断言金额 / 天数只出现账本值）、禁词表字符串断言、A5/A6 回放。
