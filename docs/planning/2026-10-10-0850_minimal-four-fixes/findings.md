# 证据与结论

基点 1fc3a8e（Codex 十轮入库）。四项必改加两处复测暴露的既有缺陷，共 6 个 commit：
c785885 证据标识 / 9b658e8 R4 语义门 / e1ad563 问句先对事实 / 4cecc95 完成状态一处定义 / cd872e2 authority 投影 / de95b82 案件迁移边。

## 三轮真实复测（同一 63 单，真实模型与知识库）

| 轮 | 镜像 | intent | sop | forbid | node_failed | 报告 |
| --- | --- | --- | --- | --- | --- | --- |
| 1853 终测（基线） | e39dd75 | 98% | 87% | 0 | 0 | 2026-10-09-1605/retest-1853 |
| 第 1 轮 | 4cecc95 | 100% | 86% | 0 | 2（T40 / T42） | retest-013041 |
| 第 2 轮 | cd872e2 | 100% | 86% | 0 | 2（T18 / T23） | retest-020227 |
| 第 3 轮 | de95b82 | 100% | 84% | 0 | 0 | retest-021644 |

sop 数字的 ✗ 几乎全是 E 类（驱动在事实问句处停下记 explain），三轮各 9–10 单，成员随模型 needs_confirmation 轮次波动
（T20 / T21 / T39 / T41 / T43 / T56 / T57 / T62 稳定，T38 / T40 / T50 轮次波动）。它不是本轮目标的尺子，目标按逐单核对。

## 四项目标逐单核对（第 3 轮）

| 目标 | 证据 | 结论 |
| --- | --- | --- |
| T23 不再 R4 | 三轮均走 rv-0138 两步，escalate_reasons 无 R4；第 3 轮跳过凭证后真实 awaiting_approval | 达成 |
| T53 直落小节 | 三轮 plans_ranked[0].matched_section = "Breast pump cannot be turned on"，首卡 s2（action），guide_trace 有 question_answered_from_facts；过保后 closed_unresolved | 达成 |
| T35 正文无 id、统计已答 | 三轮正文无 UUID / 编号；analytics.session_facts.outcome = consult_answered | 达成 |
| T41 不重复追问 | 三轮问句分别为「报错具体文字」「是否有 6018 注水异常」，不再问「没拖地是否也报错」 | 达成；问句本身仍是模型自由文本（A 类） |

保护集 T1–T10 / T13 / T14 / T29 / T45 / T55 / T63 三轮终点不变（T55 第 1 轮退步，第 2 轮起恢复）。

## 复测暴露的两处既有缺陷（都不是本轮四项引入）

1. **authority 投影**（T55 第 1 轮）：非 intake 任务把 facts / step_attempts 的存储字段原样喂模型，每条事实约 250 token。
   T55 补照片一轮 synthesize 需 10.1k / 预算 7.0k，证据删到只剩 1 条仍超，候选为空 → R5。Codex 十轮前就存在，本轮多 2 条症状事实才越线。
   修后同一 checkpoint 回放 6835 token 可入模型。
2. **案件迁移边**（第 1、2 轮各 2 单 node_failed，日志共 48 次、约 20 单同路径）：排障走完未解决 + 无订单号 + 跳过凭证 →
   propose 置 escalated_summary → summarize 调 hand_off 入队，TRANSITIONS 没有 escalated_summary → awaiting_approval。
   客户看到「案件等待处理」，案件里却没有交接摘要。1853 终测同路径停在 upload_receipt 没触发。补边后第 3 轮 0 次。

## 未改、按分类记录

- T50 第 3 轮：模型把「the left one does work」标 affirmed（不是 uncertain），直接 supported bp-0020 出卡 5 步到质保。
  A 类：极性判断靠模型；服务端已有 polarity_uncertain 门，模型不标就过不了门。可选：对「does work / works fine」加确定性极性覆盖，本轮不做。
- T43 第 2 轮意图读成 product_question、第 3 轮 R5：西语「El robot está desconectado」只有 rv-0098（升级后离线）可召回，K + A 类。
- T40 第 2、3 轮命中 rv-0371 缺链接 → source_gap → R5：K 类，行为正确；第 1 轮命中 rv-0073 出卡，召回轮次波动。
- T38 第 2 轮 needs_confirmation 问清水箱、第 3 轮出卡到过保：轮次波动。
