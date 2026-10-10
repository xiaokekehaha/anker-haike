# 勘误与回顾

## 与 plan.md 的偏差

- P1-2 最终规则：对象 / 时机冲突类澄清（reason 以 _mismatch 结尾）答过一次后，同类冲突不再追问，换对象也不问；
  needs_confirmation 的前提确认保留 R7 预算内的二次追问。原因：真实复跑里 T52 问完「盒子自身指示灯」又换候选问「泵自身指示灯」，按问句去重挡不住。
- 输入预算按用户决定提高：max_input_tokens 8000→16000、intake 16000→32000（config/conversation.yaml）；
  4 个测试改为从配置读预算，不再写死数值。用户确认效果优先、不担心预算。
- 63 单真实复测由 Codex 执行，本任务只做 4 个多轮场景复跑。

## 多轮场景真实复跑（make up 后，第二轮一律文字消息）

| 案例 | 修复前 | 复跑 |
| --- | --- | --- |
| T22 | 重发 s1 禁区卡 | 第二轮发 s2 重启（fact_check：s1 negated、s2 satisfied，引文逐字） |
| T46 | 文字回答被回「nothing waiting」 | 第二轮发 s3（模型同时给 feedback=solved 与 step_answer，按 step_answer 提交） |
| T52 | 原样重问指示灯 | 首轮问一次盒子自身指示灯；第二轮不再追问，无适用指南转人工 |
| T48 | 型号句覆盖绿灯问题 | 未改，仍覆盖（不在本任务范围） |

T22 第二轮模型没给 feedback（判为 report_problem），卡因新症状撤销后重新检索，由 fact_check 选到 s2；结果正确，但 s1 没有记反馈。
