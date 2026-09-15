# 55: 服务上下文节点与 ContextCard（凭证子流程并入）

**What to build:** `service_context` 节点：汇总 `region_purchase / region_use / channel / platform`（来源优先级：凭证事实 > 用户陈述 facts(kind=context) > 卡片），每字段记 `source`；调 `PolicyEngine.decide()` 看 `missing_inputs`；缺则 `prepare_context → await_input` 发 `context_card`（选项来自 `regions.yaml`，预填已知项），`apply_action(confirm_context)` 写回并路由 `propose`。`route_escalate`：R1/R1b/R1c/R2/R6 且 confirmed_sku → `service_context`；凭证收集 / OCR / 确认 / L1–L6 成为其子步骤（未上传凭证时先发凭证请求，跳过凭证仍可走 ContextCard 手填，但 `receipt_status` 影响授权门）。interpret 增加 `FactCandidate.kind=context` 与字段抽取。

**Blocked by:** 51, 54

**Status:** todo

**Owner:** —

- [ ] 凭证已核实（订单表含 region/platform）时不发 ContextCard 直接进 propose
- [ ] 缺 region_use 时只问缺项；用户文本「我在德国用」被抽为 context 事实并免卡
- [ ] A3 回归：R3/R4/R7/R8 仍直接 summarize，不经 service_context
- [ ] `service_context` 与 `receipt` 状态进快照与摘要

**设计依据：** 02 §2.1–2.2；04 §2、§5；06 §3
