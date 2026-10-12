# 文字追问的回答由服务端绑定

## 问题

系统提问有两种通道，回答的绑定方式不同：

```
              待答状态                 回答如何绑定
卡片问句      pending_card             card_id + input_token，resolve_command 校验 kind
文字追问      clarification            无统一绑定；回答能否回到诊断取决于 intake 的意图标签
              + diagnose_outcome
```

会话 44ba4626（2026-10-12 14:15，发布前代码）：

```
第 1 轮  系统: Is the door latch of the dirty water tank fastened securely?   （文字，无卡）
第 2 轮  用户: yes
         intake: step_feedback, feedback=solved, feedback_quote="yes"   （无卡却造了步骤反馈）
         reduce.py:524      step_feedback → mode=diagnose               （到此本可回诊断）
         commands.py:39-41  有 feedback、无 pending_card → "There's nothing waiting..."
         graph.py:1353      reply_mode=clarify
         graph.py:1544      intent 不在 {answer_pending, supplement} → dialogue
         graph.py:1199      同一轮又把 yes 记进 precondition_answers    （两处判断相反）
第 3 轮  用户: yes → intake 判 feedback=not_solved，结果同上
```

同一句 yes 在不同会话被判成 report_problem / answer_pending / step_feedback。本地 analytics.node_runs，
文字追问后的下一轮：report_problem→disambiguate 46，answer_pending→disambiguate 5，step_feedback→dialogue 1。
51 次正常里 46 次走的是「报告故障」的路，不是回答通道。

同类修补：6919d2f、e1ad563、c5ffc5a、0a2adde、fbc3427、bdadf1e。graph.py 另有 1166 / 1514 / 1529 / 1531 / 1544
五处用不同的意图白名单判断「是否在回复某个待办」。

## 目标

文字追问发出后，系统记得「在等这个问题的答案」；下一句只要不是明确的其他诉求，就作为回答回到诊断，
与 intake 给出的意图标签无关。

不改 contracts、前端、数据库。不改澄清次数预算（R7）与「冲突类澄清只问一次」。

## 设计

### 1. 待答判定：`awaiting_text_answer(state) -> dict | None`

放在 `app/sessions/clarify.py`，返回待答的 clarification，否则 None。全部满足时为待答：

- `clarification.question` 非空；
- 最后一条助手消息（history 中 role=assistant、kind=message）的文本等于该 question——沿用
  `l3_intents.product_question_answer` 的判法：之后系统说过别的话，旧问题不再待答；
- `pending_card` 为空（有卡时卡片优先）；
- `escalate_reason` 为空，`stage` 不在 {awaiting_human, done}。

以 `clarification` 为唯一待答状态，不新增字段。`diagnose_outcome.mode == "clarify"` 不作条件：disambiguate 阶段的
产品 / 症状 / 冲突追问只写 clarification，首轮 diagnose_outcome 为空，同样需要绑定。

覆盖的发问来源（均经 clarify 节点写 clarification.question）：needs_confirmation、*_mismatch、
charging_recipient_*、unparsed_problem、symptom_missing、vague_symptom、source_gap 后备追问、disambiguate 的
product / symptom / conflict 文字追问。不覆盖（各有状态位与分支，本次不动）：consult 缺参、human_request_info、
requested_remedy 补材料、操作条件（interpret.py:404 已确定性处理）、reopening、安全确认。

### 2. commands.py：待答时不再回 "nothing waiting"

`resolve_command`：无 `pending_card` 且 `awaiting_text_answer` 为真 → 返回 `(None, None)`，这句话按文字回答走
诊断，feedback / pending_answer 丢弃（无卡时它们没有指向对象）。不待答时保持原文案。

这一步必须先做：否则 1353 写入 reply_mode=clarify，路由即使改对，用户仍看到 "nothing waiting"。

### 3. 路由：graph.py:1543-1545

```
if decision.reply_mode in {dialogue, clarify}:
    if awaiting_text_answer(state) and allowed_operations
       and intent not in CONVERSATIONAL and not intake_degraded:
        return "disambiguate"
    ...（原有图片分支与 dialogue）
```

- `CONVERSATIONAL = {history_query, explain, handoff_status, social, preference, complaint, new_issue, resume_issue}`：
  用户明确在问别的，回答留到下一轮，待答状态保留。
- request_human、退换货、consult、product_question、escalation_trigger 在 1482-1526 已先返回，无需列入。
- `intake_degraded`：interpret.py:439-453 理解失败时给出的说明文案要让用户看到，保持 dialogue。
- 删除原 `diagnose_outcome.mode == clarify and intent in {answer_pending, supplement}` 条件。

reply_mode=diagnose 的情况（report_problem 等）现已落到 1550 disambiguate，不变。

### 4. 记录回答：graph.py:1199

条件改为：`awaiting_text_answer(state)` 为真、`clarification.reason == "applicability"`、
`diagnose_outcome.reason == "needs_confirmation"`、同一 issue、本轮有文字。记账范围不扩大（只有前提追问需要
precondition_answers），但与路由共用同一个判定，不再出现「记了回答却不回诊断」。

### 5. 回答必须进 synthesize：graph.py:350 `_after_product`

回答「yes」通常不产生新事实，issue_revision 不变、plans_ranked 非空时会走 reassess，回答进不了 synthesize
（代码推断，未复现；answer_pending 现已有同样风险）。本轮是对前提追问的回答时跳过 reassess 短路，直接 retrieve。
判定用进入 disambiguate 之前的状态（本轮 understand 新写入的 precondition_answers），不在 _after_product 里重算
awaiting_text_answer（clarify 节点尚未改写 clarification，但 history 已追加用户消息，最后助手消息判法仍成立）。

### 6. 清理 clarification

已核对：会话 42e7fb2c / db271c7b 回答后 clarification 已为 null（disambiguate 的 symptom_decision continue 分支，
clarify.py:230 清空）；44ba4626 因从未进 disambiguate 而残留。所以「永不清」只发生在回答没回到诊断时，第 3 节
修好后自然消失。另在出步骤卡（graph.py _diagnose_outcome evidence 分支）与转人工时显式清空，作为兜底：
`in_clarify=bool(clarification)`（graph.py:2132）会关闭检索改写，残留会影响后续检索。

### 7. intake 提示词（可选）

interpret.py INSTRUCTION 加一句：clarification.question 待答且无卡时，短答（yes / no / 不确定）是对该问题的回答，
用 answer_pending，不填 feedback。第 2–4 节已让结果与标签无关；此条只减少错误标签，不作正确性依赖。

## 测试

新文件 `orchestrator/tests/test_text_question_answer.py`（HTTP 链路，FakeChatModel），会话 44ba4626 回归：

1. 前提追问后 intake 返回 `step_feedback + feedback=solved + feedback_quote="yes"`，无卡 → 不出现
   "nothing waiting"，synthesize 被再次调用，precondition_answers 记一条。
2. 同上，intake 分别返回 report_problem / answer_pending / unknown / supplement → 均回到诊断。
3. 追问后用户问 history_query / explain → 走 dialogue，clarification 保留；下一句回答仍回诊断。
4. 追问后用户 request_human → 转人工优先。
5. 追问后系统又说了别的话（最后助手消息 ≠ question）→ 不视为待答。
6. 有 pending_card 时 → 卡片优先，原 resolve_command 行为不变。
7. 回答「yes」不产生新事实时，下一轮仍调用 synthesize（第 5 节）。
8. intake 降级（理解失败文案）→ 保持 dialogue，用户看到说明。
9. R7：前提追问答「不确定」再问一次，第二次后交人工——沿用 test_unknown_conditions_have_bounded_questions，
   确认不受影响。

回归跑：test_diagnosis_recovery.py、test_question_before_fact.py、test_in_plan_precondition.py、
test_knowledge_source_gaps.py、test_conversation_round5_boundaries.py，以及 grep 到 clarification / answer_pending
的其余测试文件。

## 改动范围

- `app/sessions/clarify.py`：新增 awaiting_text_answer。
- `app/conversation/commands.py`：第 2 节。
- `app/sessions/graph.py`：第 3、4、5、6 节。
- `app/conversation/interpret.py`：第 7 节（可选）。
- 新测试文件一个。

## 不做

- 不复用 pending_card：它表示「有 card_id + input_token 的受控命令」，前端据此停靠卡片并进入 awaiting_input；
  后端约 30 处按 kind 分支、10 余处按有无判断，文字追问没有命令 schema。
- 不合并 consult / human_request_info / requested_remedy 的意图白名单（graph.py:1514-1531）：各有状态位，
  分支在 1543 之前，另行评估。
- 不改 R7 预算与 mismatch 只问一次（graph.py:2407-2413）：attempts 只在再次发问时 +1。

## 复核

方案经 Fable 5.1 只读复核（2026-10-12）。采纳其修正：直接触发点在 commands.py:39-41；以 clarification 为待答状态并
沿用 product_question_answer 的「最后助手消息」判法；补 _after_product 的 reassess 短路与 intake 降级文案两处风险。
其「applicability 的 clarification 永不清空」一条经 checkpoint 核对为部分成立，见第 6 节。

## 实施记录（2026-10-12）

- 第 1–6 节已实施。判定在 understand 内算一次，写入 `turn_decision.answers_text_question`，路由（第 3 节）、
  记录回答（第 4 节）、跳过 reassess（第 5 节）共用。CONVERSATIONAL_INTENTS 与 awaiting_text_answer 同放 clarify.py。
- 问句前后可能附安抚语 / 转人工提示（acknowledge_current_turn），「最后助手消息就是该问题」按包含判断。
- 第 7 节未实施：加一句提示词后 intake system 超出 test_context_capacity 的上下文预算（3465+1207 > 4630）。
  第 2–5 节已让结果与意图标签无关，此条只是减少错误标签，不值得为它放宽预算。
- 测试 `tests/test_text_question_answer.py` 17 个用例。撤掉 commands.py 与路由修改时其中 4 个失败（44ba4626 的
  两种 step_feedback、unknown、resolve_command 单测），确认覆盖原缺陷。相关 42 个测试文件 613 个用例通过。
