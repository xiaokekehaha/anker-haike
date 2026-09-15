# 78: 检索评测集标注与六开关逐项启用

**What to build:** 完成 `data/eval/retrieval/cases.yaml` 56 条标注（期望文档 / 片段 / plan），扩到 ≥ 80 条含真实工单口语；按 [switches.md](../../2026-09-13_bounded-agentic-rag/switches.md) 建议顺序对照评测：`faq` → `multi_query` → `parent_expand` → `rerank` → `grade` → `query_rewrite`，每项单独开、记录 hit@5 / chunk_hit / plan_match（经 synthesize）/ 延迟 / 成本，达标（plan_match 不降、延迟 P95 在预算内）即在 `retrieval.yaml` 启用并写入 RELEASE；未达标记录原因保持关闭。

**Blocked by:** 71（真实口语样本）；P0 64（评测 CLI）

**Status:** todo

**Owner:** —

- [ ] 每个开关一份对照报告 `reports/retrieval/switch_<name>.md`
- [ ] 启用后 A1–A9 回放不退化；延迟预算断言
- [ ] `query_rewrite` 若仍 < 90% 保持关闭并在报告说明

**设计依据：** 差距分析 §1 L1；bounded-agentic-rag 阶段 3
