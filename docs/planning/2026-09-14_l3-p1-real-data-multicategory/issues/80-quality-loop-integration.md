# 80: 服务质量闭环 P0a / P0b 对接

**What to build:** 按 [service-quality-loop/design.md §7–§9](../../2026-09-13_service-quality-loop/design.md)：`satisfaction_ratings` 迁入 `quality_feedback`（type=satisfaction）并保留视图兼容；新增 `service_episodes`、`quality_cases`、`quality_events`（outbox 语义）；回答 / 步骤差评入口 `POST /sessions/{id}/feedback`；规则候选（差评、越权尝试、gate fail、stalled、complaint_risk 未解决）自动建 quality_case；admin 案例队列 / 详情复用票 60 的 CaseDetail 布局；托管率 / NSS 改从 episode 口径计算。

**Blocked by:** P0 59, 60, 64

**Status:** todo

**Owner:** —

- [ ] 同一评价重试不重复计数；修改有历史
- [ ] checkpoint 已提交但质量事件未写的故障注入 → 恢复扫描补齐且不重复
- [ ] Dashboard 指标口径切换前后数值对照报告

**设计依据：** 05 §5；07 §3；service-quality-loop §7–§9
