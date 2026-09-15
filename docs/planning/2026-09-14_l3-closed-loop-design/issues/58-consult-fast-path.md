# 58: 简单咨询快路径（查物流 / 查保修）

**What to build:** interpret `Intent += logistics_query|warranty_query|order_query|address_update|replacement_request|refund_request|confirm_received|rate`；`config/rules/intent_terms.yaml` 关键词回退；`route_entry`：`primary_intent ∈ CONSULT_INTENTS → consult`。`consult` 节点：`params.py` 从本轮文本 + facts 抽订单号 / 单号（模型任务 `consult.extract_params` 仅在正则失败且文本含数字串时调用）；缺参 → `dialogue` 文本追问（clarification reason=param，受 R7）；有参 → `executor.run(logistics.query|warranty.check)`（只读，幂等键 session:run:kind:hash）→ 回答模板 + 「来源：物流系统（模拟）」/ 条款引用 → `reply.stream` 仅润色一句开场，不改事实。`warranty.check` 调政策引擎输出保修至 / 可享补救。NotFound / Unavailable → 固定诚实文案 + 人工选项。

**Blocked by:** 51, 53

**Status:** todo

**Owner:** —

- [ ] A4：「我的换货单 DEMO-X10-001 到哪了」一轮完成；无 retrieve / disambiguate 调用；tool_call 事件成对
- [ ] 缺订单号 → 追问一次 → 用户补号 → 完成；两次仍缺 → R7 摘要
- [ ] 订单不存在 → 固定文案，不出现编造状态（断言回答只含模板字段）
- [ ] 意图评测：semantic-gold 新增 8 族 × 5 表达，accuracy ≥ 90%（domestic 链）

**设计依据：** 02 §2.1；03 §7；06 §3、§5；00 D-L3-13
