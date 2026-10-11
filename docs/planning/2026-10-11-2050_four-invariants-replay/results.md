# 四条不变式修复的真实回放

时间：2026-10-11 20:45–20:50（北京时间）。来源：`docs/planning/2026-10-11-1712_official-63-evaluation` 评测的需改进案例（T4 / T56 / T58）与会话 dbc144（官方 T20 原文，同一问句问了两遍）。

镜像按工作区重建；驱动复制自 `2026-10-10-2103` 轮（客户策略不变：操作卡一律「未解决」，问句 / 材料 / 人工边界停止），启动前后逐文件核对运行源码与工作区一致（runtime_unchanged / worktree_unchanged 均为 true）。会话 JSON 与驱动脚本按 .gitignore 只留本机。

## 根因与修复

| 不变式 | 违反的案例 | 根因 | 修复 |
| --- | --- | --- | --- |
| 客户答过的问题是证据，不再问第二遍 | dbc144 / T20 | 客户对 synthesize 前提追问的回答没有记成任何状态；下一轮重新 synthesize，「已回答的不重复问」只靠提示词，模型给出同一句就再问（0a2adde 保留了「答不确定可再问一次」，但不看答的是什么） | 回答记进问题级 `precondition_answers`（计划、前提原话、问句、回答），作为 `answered_preconditions` 交给 synthesize；同一计划同一前提再被提出时不发问，模型看了回答仍确认不了前提就丢弃该候选（`precondition_unconfirmed`） |
| 每次停下都给出真实原因和下一步 | T56 / T58 | 首封粗口 → angry → `prefer_proposal_over_more_steps`；两步后 `decide_next` 压掉本来要发的 s3，返回 `operation_conditions_unavailable`，文案是「I can't confirm the cause yet」，并不缺任何操作条件 | 情绪止步单独的原因 `emotion_prefer_proposal`，文案给「转人工 / 回复 continue 继续官方步骤」；说过继续后不再拦 |
| 情绪不是现象 | T58 | intake 把「You're fucking cameras suck」抽成现象 poor quality；`concrete()` 只拦愿望句 | 引文去掉情绪词（情绪分级同一份词表）后只剩指代整机的词，判为评价，不算现象，候选按 `not_concrete` 丢弃并追问现象；情绪词修饰部件 / 现象（「the suction is terrible」「吸力太烂了」）仍是现象 |
| 步骤类型按客户交付什么判 | T58 | bp-0199「Donate a video for further analysis」的动词不在交付动词表，判成操作卡，问「解决了吗」 | donate / submit 并入交付动词；全库 1364 段只有 bp-0199#2 类型改变 |

顺带：物流回执记运单号与承运商（T4 重复 1 说「Tracking number / Carrier: no confirmed record」，订单里有 Australia Post 运单）；`facts.context_field` 枚举外的值只丢该字段，不让整轮 intake 校验失败重试（T4 三次运行都先 schema_error）；读图「其他」不回显（dbc144「base station 其他」）。

## T4 为什么之前对、17:12 轮错

历史 8 轮与本次 3 轮的 intake 都会顺手列订单字段（seller / purchase_date）。区别在 `answer_request.quote` 是否逐字出自原文：不逐字时 reduce 整个丢掉 answer_request，consult 走默认物流查询（对）；逐字时保留，consult 按字段列购买信息（错）。之前答对是引文碰巧没过校验。另一会话把 consult 改为物流诉求一律先查包裹（未提交，与本次修改同一工作区），本轮 T4 3/3 走物流方案。

剩余：「previously had got one from good guys」仍被记成本单 seller 事实，answer_request 带订单字段时答复尾部会附「Seller: good guys」。本轮 3 次都没出现（模型没列订单字段），未修，需与 consult 的字段约定一并决定。

## 定向重放（每单 3 个独立会话）

| 案例 | 结果 | 判定 |
| --- | --- | --- |
| T4 | 3/3：Australia Post 运单 + 承运商调查方案卡，无购买信息列表 | 通过 |
| T20 首轮 | 3/3 先问前提（是否从基站出发 / 是否同楼层），问法各不相同 | 合理澄清 |
| T20 每问答 yes | 3/3 无重复问句；两次发 rv-0218 s1，一次发 rv-0087 s2 | 通过（dbc144 修复） |
| T56 | 2/3 走 bp-0151 两步后出「human agent / continue」二选一；1/3 首轮先问电量 | 通过 |
| T58 | 3/3 追问设备表现，不选画质指南 | 通过 |

## 63 单主层（与 17:12 轮逐单比较首卡、停止原因、阶段、方案卡）

56 单一致，7 单不同：

| 案例 | 变化 | 原因 |
| --- | --- | --- |
| T4 | 购买信息列表 → 物流方案 | 预期（另一会话的 consult 改动 + 本次回执字段） |
| T56 | 操作条件暂停 → 情绪止步二选一（本轮选 bp-0151，17:12 为 bp-0186） | 预期；候选指南不同属 synthesize 波动 |
| T58 | 画质指南 → 追问现象 | 预期（`not_concrete` 丢弃 6 条候选） |
| T35 | 说明后 done → 同样说明正常行为、停在 intake | 路径为 product_help（产品咨询），本次改动未触发；模型把首封判成 product_question 而非 report_problem |
| T36 | 首卡 rv-0341 问句 → synthesize 先问同一问题（「拆下滚刷后噪音是否消失」） | synthesize 判待确认，问法与卡片一致；本次改动未触发 |
| T38 | 首轮问水箱 → 直接发 rv-0023 并走到问句 | synthesize 判 supported；本次改动未触发 |
| T40 | 发 rv-0073 后要凭证 → rv-0371 判资料缺口 R5 交人工 | 候选指南不同；rv-0371 原文引用了未给出的说明，source_gap 交人工是既有行为；本次改动未触发 |

新规则只在 T56（情绪止步）、T58（not_concrete）触发；`precondition_unconfirmed` 主层无触发（首轮追问即停）。

单测：dbc144 重复提问（去掉修复失败）、答「不确定」可换问法再问、情绪止步原因与文案、评价不算现象（含中文与防误伤）、bp-0199 类型、context_field 容错、读图「其他」不回显；ci-local 全绿（后端 1296、契约 91、前端 230）。
