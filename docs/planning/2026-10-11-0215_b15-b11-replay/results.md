# B15 / B11 修复、rationale 截断；B18 未改

时间：2026-10-11 01:30–02:25（北京时间）。来源：`docs/planning/2026-10-10-2103_official-63-continuation/issue-register.md`「补测确认的对象问题」。

## 根因与修复

| 案例 | 根因 | 修复 |
| --- | --- | --- |
| B15 / T53 | 过保拒绝后案件 closed_unresolved；客户「I understand the replacement warranty has expired. Please still help me troubleshoot」被 `reopening_request` 用症状引文认作「已结案件再次求助」→ 重开 → 再走质保再拒一次，排障任务也一起结束 | 案件因过保 / 非授权经销商结案、本轮不是换货退款诉求时不重开：资格结论不会因为再描述一次故障而改变，按排障继续 |
| B11 / T52 | 客户「My charging case will not charge therefore I cannot charge my pump motors」。`check_charging_recipient` 用下游事实「泵充不上」把 bp-0122「泵马达不充电」判 matched；「盒灯不亮」又被当作前提已知直接出卡 | 已有事实说充电盒自身不进电时，讲泵受电的条目判 mismatch（供电源头没解决） |
| B25 第二次回放 | synthesize 的 rationale 超 80 字，deepseek 两次 schema_error，整批作废 → R5 | 自由说明字段超长截断，不让整批作废；schema 仍写 80 字上限 |

## B18（未改）

首封「water injection is still malfunctioning we have not run mop cycles and thus havent needed any mop drying」。
21:03 轮补测里 intake 只抽出「failed drying」「water injection malfunctioning」两条症状，没把「没跑过拖地」抽成否定事实，synthesize 判 rv-0146（烘不干，要求再跑拖地）supported 0.6。
同一原文主层 T41 判 needs_confirmation、先追问。

试过在 intake / synthesize 提示词里加「没运行过的功能抽成 negated 事实、依赖它的候选 not_applicable」，用真实模型对同一原文测 1 次：
intake 仍没抽出否定事实，synthesize 判 rv-0146 needs_confirmation（与改前主层一致）。样本不足以说明提示词有效，已撤回，不提交未验证的提示词改动。
B18 的波动在 synthesize 对 rv-0146 的 supported / needs_confirmation 判定上，是否值得加确定性规则（如候选要求「perform a new mopping task」而用户说没跑过拖地）待定。

## 真实回放（镜像重建后）

| 案例 | 会话 | 实际 | 判定 |
| --- | --- | --- | --- |
| B15 | 553f72a2 | 首轮过保拒绝 + 发 bp-0114 s2；第二轮「理解过保，继续排障」→ 不重开、不再拒，继续发 s2 卡 | 通过（s2 是同一张待答卡重发；客户还没反馈它） |
| B11 | fd408511 | 先问盒灯 → 答「盒自身接电灯不亮」→ bp-0039 / bp-0067 / bp-0122 判对象不符，bp-0127（单侧不充）前提不成立 → 如实说找不到适用指南并交人工 | 通过：不再发泵重置、清磁吸头卡；本地 875 条 Q&A 没有「充电盒自身不进电」指南，属资料缺口 |

单测：B15（去掉修复失败）、B11、rationale 截断各一条；ci-local 全绿（后端 1267、契约 91、前端 230）。
