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

## T22 复测不稳定（Codex round-02 B06-r2）与修复

问题：第二轮意图模型同时给出 step_feedback，P1 把 s1 记 not_solved、游标推进到 s2；fact_check 只把 s2 一条条件给模型，
模型把原话里「has not been stuck at stairs」的否定套到平地条件上，判 s2 negated；引文校验只验原话存在，拦不住语义错。
跳过 s2 后计划耗尽（MAX_GUIDES=1）→ 转人工 → 进质保要订单。成功轮 B06-r1 没有反馈，s1、s2 同时给模型，判对。

两处设计缺陷：只给孤立条件、没有对照；一次轻量判定「不成立」就能让计划耗尽，错跳代价远大于多发一张卡。

修复（fact_check）：
- 已处理的兄弟条件以 [reference] 一并给模型，只采纳未处理步骤的判定；提示补「否定一个场景不等于否定另一个场景」；
- 否定判定若会跳过最后一个未处理的操作步骤且没有兄弟条件成立，该步骤照发（kept=last_step）。

验证：新增 3 项（含 B06-r2 路径的 HTTP 回归，去掉保护即失败）；全量 1187 passed / 2 skipped；
make up 后真实连跑 T22 6 次：5 次 s1 → s2；1 次首轮意图被判 product_question、未进排障（另一问题，见下）。

## 另一个 T22 问题：首轮 App 报错表单被判成 product_question

第 1 次复跑首轮意图模型把带 Probleemcode 7002 的 App 报错表单判成 product_question，走产品咨询，不发卡；
第二轮报现象时错误码只从本轮原文解析，精确命中路径没触发，synthesize 又因 rationale 超 80 字 schema 失败三次，最终转人工。
用户决定一起修：
- interpret.device_code_report：App 报错表单带错误码时，product_question 改为 report_problem（官方 63 单 17 张带码表单金标全是 report_problem），接在 logistics_correction 共用入口；
- exact_code_hits：错误码从本问题所有事实来源的用户原话里取，首轮没进排障时后续轮次仍能精确命中。
synthesize 的 rationale 超 80 字 schema 失败未改：精确命中后不再调用 synthesize。

验证：新增 2 项（去掉任一修复即失败）；全量 1189 passed / 2 skipped；make up 后真实连跑 T22 8 次，8/8 为 s1 → s2。
其中 1 次首轮仍出现「device troubleshooting → delivery status」多诉求提示（模型给出不存在的物流次诉求，Codex 早先记录的旧现象），未处理。

## T22 首轮多出「设备排障 → 物流状态」提示

问题：意图模型给 T22 表单加了 logistics_query 次诉求，引文是 `Bron: eufy_mega\nInzenddatum: 2026-09-03T05:46:35-07:00` 两行元数据。
现有请求证据校验（ground_additional_queries）只认固定名单里的字段名（Order No / Country / Source…），且要求引文落在单行内：
Inzenddatum（提交日期）不在名单里，引文又横跨两行，于是放行，任务队列多一个物流任务，回复开头出现多诉求排序提示。

修复（request_constraints）：表单格式（app_report / rma）已识别时，凡是「字段: 值」行都算元数据（描述与推送除外，那是用户 / 设备在说话）；
引文由若干整行元数据拼成也判 metadata_is_not_request。用户在描述里写的并列请求不受影响。

验证：新增 4 项（去掉修复 3 项失败）；全量 1193 passed / 2 skipped（另有 test_outcome_boundaries 4 项真实 Postgres 用例偶发失败、重跑通过，与本改动无关）；
make up 后真实连跑 T22 首轮 12 次，0 次物流提示、12 次首卡 s1。这 12 次模型本身也没给物流次诉求，修复路径只由单测覆盖，真实环境未触发。
