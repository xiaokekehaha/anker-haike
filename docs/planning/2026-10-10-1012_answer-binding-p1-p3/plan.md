# 回答承接与条件步骤（P1 → P2 → P3）

基点：`codex/official-63-ten-rounds` 提交 cd872e2。
依据：`docs/planning/2026-10-10-0948_multiturn-reproduction/` 的完整会话、根因分析与本会话对 T22 / T46 / T52 的核对。

## 问题

系统发出的问题或步骤，与用户对它的回答之间没有绑定；每轮按事实与计划重算，而「这一问 / 这一步还要不要发」读的是另一份状态。

```
            系统发出                  用户回答落到哪               下一轮判断读什么            结果
T46 文字   问题卡 s2                事实（症状），先撤卡          resolve_command 看不到卡    "nothing waiting"
T46 原评测 synthesize 文字追问       事实                        step_attempts（空）         重发 s2 卡
T22        操作卡 s1（条件句）        事实，先撤卡                 从首步选，不核对条件         重发 s1
T52        充电对象冲突的模板追问     事实                        不读事实，冲突判定不变       原样重问
```

## P1（确定性，不加模型调用）

1. 先承接，再撤卡。文字消息里有对当前步骤卡的反馈或回答（有本轮原文引用）时，新增症状不撤卡；
   `resolve_command` 生成命令，走 `apply_action → verify` 写入 `step_attempts`。只有纠正（replace / retract）仍撤卡、仍要求确认。
   - `PendingAnswer` 增加 `step_answer`（payload: option / text），问题卡与材料卡的文字回答用它；
   - 待答卡是问题 / 材料卡而模型给了 feedback：把 feedback_quote 当作文字回答（反馈对问句没有语义）；
   - 卡片载荷校验抽成一处，HTTP 动作与文字命令共用。
2. 同一澄清不问第二次。synthesize 产出的澄清问句与上一轮已发出的澄清相同（同 reason、同问句）且本轮是用户回答时，
   丢弃该澄清；剩余候选为空时走已有出口（交接），不再发同一句。首次追问保留（T52 金标 sop=clarify）。

验收：T46 文字回答推进到 s3；T22 第二轮不出现 "nothing waiting"，反馈进入 step_attempts；T52 第二轮不重问指示灯。

## P2（追问与问题步骤读事实）

问题步骤先对事实：模型从已有事实中给出某个问题步骤的答案，并引用事实原文；服务端逐字校验后写入 `step_attempts`（source=fact），
与 e1ad563 的 matched_section 共用重放边。覆盖 T46 原评测（文字澄清已答，再进指南仍发同一问题卡）。

## P3（条件步骤，方案 A）

`plan_of` 把 "If <条件>," 开头的步骤拆出 `condition`（196 条 QA / 245 步）。计划含条件步骤、且除错误码外还有用户事实时，
调用一次轻量模型判定每个条件：satisfied / negated / unknown，必须引用事实原文，服务端逐字校验。
negated 跳过；兄弟步骤 satisfied 直接跳到该步；unknown 照常发卡。精确错误码路径同样经过此判定。

## 不改

统一的跨 intake / guide / 咨询「待答问题」状态（可一并解决 T48）；T52 重跑中 bp-0049 常规充电指南被放行的问题（充电关系核验只看标题）。

## 验证

每项 TDD，`make lint`，只跑相关测试；三项完成后 `scripts/ci-local.sh`、`make up`、4 个多轮场景与 63 单真实复测，意图 / SOP 不回退。
