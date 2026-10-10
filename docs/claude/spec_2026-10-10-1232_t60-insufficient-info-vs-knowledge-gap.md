# T60：信息不足被当成知识缺失

## 第一性原理

转人工的前提是「系统已经尽力且确实无法给出官方指引」。检索落空有两种完全不同的原因：

1. **知识缺失**：问题已经问清（型号确定、现象具体），官方资料就是没有。转人工正确。
2. **信息不足**：型号或现象没问清，检索的输入本身太泛。此时转人工只是把空摘要推给同事，客户多一轮等待；正确做法是先问。

系统现在只看「检索有没有命中」，不看「输入够不够」，于是 2 被当成 1。T60 三个问题都是这一处混淆的不同表现：首轮该问没问（问题 1）；转人工后客户补的信息没用来重试（问题 2）；交接摘要把原因写成「没有方案」（问题 3）。

## 追踪（真实 3/3 复现，容器 96d102c）

```
用户：「This app is shit. I just want my hoover to clean with out all this bullshit」
intake  事实 symptom「hoover not cleaning properly」（引文是一句愿望，模型改写成现象）
        品类 robot_vacuum（hoover 关键词），型号未知；情绪 angry → direct_resolution → skip_optional_clarify
disambiguate  category_only；型号卡被 skip_optional_clarify 跳过
retrieve  「扫地机器人 hoover not cleaning properly」，category 范围 → no_match
_diagnose_outcome  confirmed_symptom = 有一条肯定事实 → True → 不进 T60 保护 → R5
escalate  hand_off → case awaiting_approval → stage awaiting_human
第二轮「It stops halfway through cleaning and goes back to the base…」
route_after_understand  case_id 且 awaiting_human → dialogue
reply  explanation()：「Tell me more … I'll check the official guidance」← 刚说完，且不会去查
摘要  reason R5「当前产品的这一问题没有可用的排障计划」，problem 用模型改写句，business.missing=[product]，没有 symptoms 缺失
```

## 方案

### 1. 检索落空时先判断是不是信息不足（问题 1）

`_diagnose_outcome` 的 no_match 分支，把「是否有可核对现象」换成「检索输入是否充分」：

```
insufficient = 型号未确认（product_state != confirmed_sku）
               或 没有具体现象（confirmed_symptom 为假，或唯一的现象事实引文出自愿望/泛称，见下）
```

- 型号未知是结构性信号，不靠词表：同品类 6 个型号的官方 QA 按型号分化，category 范围检索本来就弱。
- 「具体现象」不做词表判断。改为：信息不足时追问的内容由缺什么决定 —— 缺型号问型号（点选型号卡，带「不确定」出口），型号已知但仍落空问现象。
- 预算沿用现有 clarification 预算（MAX_CLARIFICATIONS=2，与 disambiguate 共用），问满仍落空才转人工，原因写「信息不足」（见 3）。
- skip_optional_clarify（愤怒客户少问）只跳过「可选」的型号卡；检索已落空时型号不再可选，必须问一次。这是情绪策略本意：「仅追问必要信息」。

不改：检索命中的工单、错误码精确命中、型号已知且现象具体仍落空（真正的知识缺失）—— 这些路径照旧。

### 2. 转人工后补了信息：重新排障（问题 2，方案 A）

条件全部满足才重试，避免打断真正需要人工的案件：

- 案件状态 awaiting_approval，且交接原因是「信息不足」或「无可用方案」（R5 / R7）；
- 人工尚未作出决定（没有 decision）；
- 本轮补了新的产品身份或新的具体现象事实（issue_revision 变化且有新增 symptom / product）。

满足时：路由回 disambiguate → retrieve。命中 → 案件撤回人工队列（新增 awaiting_approval → diagnosing 迁移，记 `customer_supplied_info` 事件），发步骤卡；仍落空 → 只刷新交接摘要（record_handoff），回复说明「已补充进工单」，不再承诺去查。

不满足时（人工已接手、安全 R4、客户要求人工 R3、质保 / 订单类交接）：保持现状，只把补充内容写进摘要。

回复文案同时修：awaiting_human 下的 explanation 不再说「I'll check the official guidance」，改为说明补充内容已记入工单。

### 3. 交接摘要区分两种原因（问题 3）

- 新增原因码含义：R5 拆成「信息不足后仍未命中」（cause=insufficient_information）与「已问清仍无官方资料」（cause=knowledge_gap）；reason.text 分别写明。不新增 R 码，避免牵动评测与前端的 R5 统计，用已有的 `reason.cause` 字段区分。
- business.missing：型号未确认写 product；只有泛称或愿望、没有具体现象写 symptoms。
- problem 字段优先用客户原话中的问题描述，不用模型改写句；改写句放 observations。
- 首轮致歉文案「sorry this has taken so much of your time without a fix」只在已有排障或多轮之后使用；首轮愤怒用「I'm sorry about the frustration」类短句。

## 可选复杂度（本次不做）

- 判断「现象是否具体」的模型调用：先用型号缺失这一结构信号与「问一次现象」覆盖，复测不够再加。
- 人工已接手后的客户补充触发重派：属于人工工作台流程。

## 验证

- 单测（FakeChatModel，按真实模型输出构造：抽出一条泛化现象、型号未知、angry）：
  - T60 首轮 → 型号卡或型号追问，不转人工；补型号后仍落空 → 问现象；问满 → R5 cause=insufficient_information，missing 含 product / symptoms；
  - 型号已知 + 具体现象 + 落空 → 直接 R5 cause=knowledge_gap（现有 test_no_match_with_a_real_symptom_still_hands_off 保持）；
  - 转人工后补具体现象 → 重新检索，命中则发卡、案件回到 diagnosing；R3 / R4 / 人工已决定时不重试；
  - 摘要 problem 用原话。
- 改写现有 T60 测试的模拟输出（facts 从空改为一条泛化现象），使它代表真实模型行为。
- 后端全量、lint；make up 后真实跑 T60 多次；回归 T61（型号已知、现象具体）、T58（只有辱骂）、T13（错误码官方未收录 code_miss）不退化。

## 实施记录（与方案的偏差）

- 「具体现象」判断：先试了按词面比对 value 与引文找模型改写，对真实 89 条事实有 6 条命中，误伤 T61「going off 2 hours before」→「starts two hours early」这类正常归纳，弃用。
  改为只认引文的愿望句式（`I just want my X to …` / `我想让它…`）：这是一小类语法结构，不是现象词表；真实 89 条只命中 T60 本身与 3 条模糊或元数据引文。
- 真实复跑发现模型对 T60 有两种抽法：改写成「not cleaning properly」，或原样抄成「hoover to clean with out all this bullshit」；后者选完型号后检索有命中、全部不适用（knowledge_status=ok）。
  信息不足的判断因此同时覆盖 no_match 与「有命中但无适用方案」。
- 错误码官方未收录（T13 code_miss）标为 knowledge_gap。
- 转人工撤回的触发放在 guide 发出步骤卡时，以本轮开始时的案件状态 awaiting_approval 为准；仍未命中时 summarize 只刷新摘要，回复说明已记入工单。

## 验证结果

- 新增 tests/test_insufficient_information.py 10 项；改写既有 T60 测试的模拟输出为一条愿望式现象；T52 去重测试补上「已问清」状态。后端全量 1203 passed / 2 skipped，lint 清零。
- make up 后真实复跑：T60 3/3 首轮出型号卡，不再转人工；选 C20 后两次给官方清洁建议（explained），一次问具体现象；补「中途回基站」后 3/3 进入官方排查（问基站摆放 / 步骤卡）。
  T13 摘要 cause=knowledge_gap；T22 首卡 s1、T61 时机澄清不变。
- T58（只有辱骂）回复为情绪策略的减负话术，与本次改动无关，未处理。
