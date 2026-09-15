# 证据

## 会话事实（/admin/api/sessions/9db433.../journey）
- 4 run，42 秒（2026-09-15 16:34:55 → 16:35:37 北京时间），clarifications=2，steps_executed=0，outcome=escalated / R7。
- product_state 全程 unknown，sku=null，category=null，fault_plan_ids=[]。
- 全程没有 vision 节点、没有 retrieve 节点。model_calls=2（均为 intake）+ 1 次 disambiguate.clarify。
- run1 用户消息 text=""、image_ids=[5b17ee93...]（purpose=fault）；run2 text="有点问题" + image af68071a...，两张图 sha256 相同（d343eaa9...）。
- 摘要 observations：「R7：连续 2 次澄清（product）并收到回答后仍无法确认」；product 字段「未确认（线索：x00001）」。

## R7 触发点（全仓 4 处）
- orchestrator/app/sessions/clarify.py:198 `_clarify`：同一 reason 的 attempts ≥ MAX_CLARIFICATIONS(=2) 且本轮为对上一问的回答 → R7。本会话走这一条。
- orchestrator/app/sessions/clarify.py:182：diagnose 决策 outcome=escalate（症状不足且无可区分问题）→ R7(symptom)。
- orchestrator/app/sessions/l3.py:559：业务查询缺订单号，consult_attempts ≥ 3 → R7。
- orchestrator/app/sessions/l3.py:886 `prepare_retake`：照片重传 > 2 次仍不可辨认 → R7。

## 计数规则
- `count_attempt`（clarify.py:214）在真正发出追问或产品卡片时 attempts+1；reason 变化即归零。
- attempts 记在 reason 上，但实际问出口的文案由 ModelRouter task=disambiguate.clarify 生成，内容不受 reason 约束。

## 直达人工摘要的链路
- receipt.py:45 `DIRECT_SUMMARY_REASONS = {R3,R4,R5,R7,R8}` → `needs_collection` 为假。
- graph.py:2070 `route_escalate` → 跳过 prepare_receipt，直接 summarize。
- graph.py:2161 `summarize` 发 `escalation_summary` 事件 + `reassurance_text(reason)`。
- summary.py:173 默认文案「我已整理当前问题记录，您可以复制给人工客服继续处理。」
- frontend/src/components/SummaryCard.tsx:52 固定表头「问题摘要已整理，可复制给人工客服」。
- conversation/reply.py:42 自述「尚未接入真实人工转接服务」——R7 之后没有人接手，会话即终止。
- analytics/derive.py:16 `SYSTEM_FAILURE_RULES` 含 R7，本次计为系统失败。

## 目录与计划覆盖（只读核对）
- in_scope 品类只有 robot_vacuum；breast_pump / power_bank / charger / earbuds / security_cam 均 in_scope=False。
- `get_plans().allowed_for(category='robot_vacuum')` 非空：rv_suction_hair_wrap、rv_suction_filter_clog、
  rv_suction_dustbin_full、rv_suction_side_brush、rv_suction_motor_fault、rv_power_supply。
- `catalog.category_hint()`：'有点问题' / '运行异响' / 'x00001' 均返回 None；'扫地机器人' 返回 robot_vacuum。
- 结论：只要 category=robot_vacuum，clarify.decide 就走 category_only → continue（clarify.py:154-163），本会话不会到 R7。型号非必要条件。

## 结构性缺口
- graph.py:335-340 `_after_product`：product_state ∉ {confirmed_sku, category_only} 直接 return "reply"，读图节点排在产品确认之后 → 产品未知时永不读图。
- clarify.py:284 兜底文案要求用户「拍一张机身型号标签」，与上一条自相矛盾。
- intake/extract.py:96 只向模型传「（用户同时上传了图片）」字符串，模型看不到图；空文本输入无硬兜底，run1 回复「用户输入为空，无法识别意图或业务对象。」为模型输出的内部口径。
- catalog/service.py:193 `category_hint` 为关键词子串匹配，模型在追问里已断定「您的扫地机器人」，该理解未回流到 state.category。
