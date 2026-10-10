# 官方 63 单复测 P1：承接客户已说明的事实，不重复索取暂缺资料

来源：`docs/planning/2026-10-10-1321_official-63-continuation/ambiguities.md` 的 A06、A07、A12、A17、A30。前四条是 63 单首轮缺陷的主体（6 个里占 4 个）。

## 1. 已做过 / 已排除的步骤不再发（T16、T27、T31、T37）

问题 → 追踪：

| 单 | 客户原话 | 发出的卡 | 现有机制为何没拦住 |
| --- | --- | --- | --- |
| T16 | It is fully installed and clean | rv-0056 s1 查滤网装没装 | 唯一现象事实的引文落在表单描述字段，记为 source=device_message；fact_check 只在有 user_statement 事实时调用，整条没跑 |
| T27 | no blockage seen. roller mop area is clear | rv-0147 s1 查滚筒异物 | 没抽成 action_taken；fact_check 只核问句和带 if 条件的步骤，s1 无条件 |
| T31 | despite wiping clean the electrical connections | rv-0473 s3 擦充电触点 | 有 action_taken，但 steps.matches_reported 的部件词表把「electrical connections」映成 contact，卡上是「charging pins」→ pin，部件对不上 |
| T37 | Terwijl de schoonwater tank nog vol is | rv-0021 s1 空箱加水 | 「水箱满」是反证，不是已做的动作，词表机制天然不覆盖；且 s1 无条件 |

方案：沿用已有的 `guide/fact_check.py`（进指南前用客户原话核对步骤，模型只给判定 + 逐字引文，服务端校验），扩一种判定：

- 候选步骤从「问句 + 带条件的操作」扩到全部操作步骤；提示词给出步骤原文（截 400 字）。
- 新判定 `done`：原话表明已做过这一步，或已确认这一步要查的情况不存在（提示词给出例子：用户说水箱满，对「检查有没有水，没有就加水」是 done；第一轮回放模型对荷兰语 T37 判 unknown，加例子后判 done）。引文必须逐字出自客户原话，且不能只落在设备推送字段里（T16 的「Please insert dustbin and filter」是设备在说话）。
- `done` 的步骤跳过，并且可以让计划耗尽：客户自述试过仍未解决，按 SOP 进质保判断。条件否定（negated）仍保留「最后一步照发」的保护，因为那是模型对场景的推断，`done` 是客户自己的陈述。
- 调用门槛从「有 user_statement 事实」改为「客户自己写过话」：有自述事实，或表单的问题描述字段不只是推送原文。

为什么不扩 `matches_reported` 词表：T27、T37 是「看过没问题 / 状态相反」，不是同名动作，词表补不出来；T31 补一个同义词能修一单，但下一单换个说法又漏。fact_check 已经是这类判断的入口，只是覆盖面窄。

代价：每个计划多一次 guide.step 模型调用（同一事实修订号下每个计划只判一次，已有缓存）。模型判错的方向：误判 done 会少发一步，客户回「未解决」时仍进质保；误判 unknown 回到现状。

## 2. 客户说暂时没有单号 / 凭证时不逐字重复（B12、B17）

问题：B12 第二轮「I don't have the order number or tracking number with me right now」，B17 第二轮「I don't have my receipt right now. Do not submit any replacement request yet」，系统都原样再发一遍索取句。

方案：`sessions/l3.py` 的 `LACKS_IDENTIFIER` 识别「没有 / 找不到 / 丢了」+ 单号或凭证名词（英、荷、德、法、西、中）。必须同时出现名词：第一轮回放中 T31「the robot can't get past critical low battery」被宽泛的 can't get 误判为缺资料。命中时：

- 物流查询缺单号 → `TRACKING_LATER`：说明查不了、单号在哪找、补上即查。
- 质保缺订单 / 凭证 → `PROOF_LATER`：说明查不了保修、现在不会提交任何申请、订单号与凭证去哪找、补上从此处继续。

资料仍是必需的，不改 SOP 分支、不改 consult 的追问计数（3 次后仍按 R7 交人工）。

## 测试

- `tests/test_step_fact_check.py`：done 引文不能是推送原文、无条件步骤不接受条件判定、done 可耗尽计划、T16 直接到磁铁检查、只有推送原文时不调用核对、T37 不发加水卡并耗尽计划。
- `tests/test_missing_identifier_replies.py`：识别正反例、B12 第二轮回 TRACKING_LATER、B17 第二轮回 PROOF_LATER 且无方案 / 执行卡。

真实回放见 `docs/planning/2026-10-10-1510_p1-fact-carryover-replay/`。
