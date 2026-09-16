# 实施附录（第一阶段）

## 与 design.md 的偏差与解释

1. **追问的落地方式**：设计只定义 `ask` 决策。实施上 `ask_observation` 节点以固定文案（问题 + 选项）发出消息，用户自由文本由 `observations.match_reply` 匹配唯一选项（标签或配置的 phrases，带否定前缀保护）；匹配多个或没有命中不写事实，换一种表达再问一次，仍无结果记为 `observation_unavailable`。没有引入新的卡片类型。
2. **候选范围**：为保持其他计划行为可回放，候选仍以 `plans_ranked` ≥ 0.3 为主，只新增「被观察解锁」的计划（requires_observations 满足）。问诊期的计划约束（constrain_plans）只作用于模型排序候选，观察解锁的计划以观察条件 + 症状码为门槛。
3. **步骤卡上的观察**：用户已通过问诊或事实提供过的观察不会再出现在卡片上（`guide/steps._open_observations`）。
4. **`exhaust_plan` 语义变化**：不再切换计划或返回 R2，只标记耗尽并返回 `reassess`。`switch_plan`/`step_dropped` 的 trace 由 `_apply_next_action` 补发，现有 test_guide 断言不变。
5. **R2 兼容**：`escalate_reason` 仍写 R2（analytics、route_escalate、receipt 收集等依赖），真实原因在 `next_action.reason` 与 `EscalationReason.cause`。

## 部署注意

- 计划配置版本 `2026-09-16.1`，`rv_power_supply` v2：部署后需 `make seed WHAT=plans` 同步 plans 表（steps 为 jsonb，含 observations）。
- 旧客户端不带 `observations` 字段仍可正常反馈；旧步骤卡（无 observations）反馈里携带的观察会被忽略。

## 验收对照（design §6）

| 验收项 | 覆盖测试 |
| --- | --- |
| f30 两次未解决可解释 | `test_f30_replay_records_observations_and_explains_the_end`、`test_f30_two_unresolved_steps_end_with_explicit_coverage_boundary` |
| 相同未解决、不同观察 → 不同候选；无配置不编造 | `test_same_not_solved_with_different_observations_yields_different_paths`、`test_observation_unlocks_a_verified_path_without_restarting_the_plan` |
| unknown / cannot_do / 未观察完不写阴性 | `test_record_observations_dedupes_supersedes_and_ignores_unknown`、`test_observation_gate_treats_unknown_as_missing_not_negative` |
| 早已提供充电指示不重问；纠正后重新评估 | `test_interview_answer_is_reused_as_observation_without_new_fact`、`test_missing_observation_is_asked_once_per_attempt_then_declared_unavailable` |
| 不重复已执行动作 / 不重启耗尽计划 / 能停下 | `test_ranked_switch_keeps_confidence_threshold_and_skips_executed_steps`、`test_user_unable_to_observe_ends_with_observation_unavailable` |
| 风险 / 主动人工 / 确认恢复优先；prepared 不显示为已接入 | `test_risk_human_and_resolution_take_precedence_over_steps`、前端 `SummaryCard.reason.test.tsx` |
| 使用公开接口与真实事件入口 | `tests/test_diagnostic_loop.py` 全部 API 测试均走 `/sessions/{id}/messages|actions` |
