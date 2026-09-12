# 32: 假设汇总 plans_ranked

**What to build:** 文本 query 检索与读图并行；观察有新增信息时补一次检索（可选 task，预算不足跳过）。synthesize 任务（强推理档）输出最多 3 个假设，每个必须引用当前允许集合内的 plan_id 与 evidence_ids，无对应计划的假设丢弃；写入 plans_ranked 与 retrieval_trace。

**Blocked by:** 28（tool_call 与 evidence 事件 + EvidenceDrawer）、30（读图观察 diagnose.vision）、31（预写排障计划表与 seed）

**Status:** ready-for-agent

- [ ] A1 输入下 plans_ranked 首位为毛发缠绕计划
- [ ] 输出中不在枚举内的 plan_id 被丢弃并记录
- [ ] 并行执行的读图与检索用 LangGraph reducer 合并到不同字段（无覆盖）
- [ ] 第二次检索在剩余预算 < 3 s 时被跳过并记录

**设计依据：** 03 §1.4；09 §3.2；07 §16
