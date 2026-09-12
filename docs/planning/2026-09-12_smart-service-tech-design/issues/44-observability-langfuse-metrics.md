# 44: 可观测：Langfuse profile 与延迟指标

**What to build:** Langfuse 作为 compose 可选 profile；ModelRouter 每次调用写 Langfuse（输入、输出、延迟、token、model_used、attempts）；状态迁移、检索、规则判定写结构化 JSONL；埋点 first_visible_ms 与 card_ready_ms 并可按会话汇总；关闭 Langfuse 时只写日志。

**Blocked by:** 12（限流退避与全局有界队列）、28（tool_call 与 evidence 事件 + EvidenceDrawer）

**Status:** done（2026-09-12，在线/离线联调与 88 项相关回归通过）

**Owner:** Codex（2026-09-12 23:29 起实现：`orchestrator/app/observability/`、`deploy/observability/`、`haike-metrics` CLI，记录见 ../../2026-09-12_observability-continuation/。Claude Code C 23:25 曾认领，发现并行后于 23:40 让出，未留改动）

- [x] 开启 profile 后一次 A1 会话在 Langfuse 中按 session_id 串联全部调用
- [x] 关闭 profile 时无报错且结构化日志完整
- [x] 有脚本从日志汇总 first_visible_ms / card_ready_ms P50 / P95
- [x] 日志中手机号与订单号脱敏

**设计依据：** 04 §3；07 §15

**并行部署贡献：** Codex（2026-09-12）：`deploy/observability/` 独立 Compose、私有本地凭据初始化、Langfuse 4.35.0 与 Chainguard MinIO 固定 digest、部署联调。Claude C 已让出票据，核心统一采用 Codex 的 `app/observability/` 实现。

**验收记录（Codex，2026-09-12）：** 本机 Langfuse 4.35.0 health=OK，6 个独立依赖/服务运行（5 项配置了 healthcheck，均 healthy）。真实 A1 首轮图 + 假模型/知识库运行至 step_card / awaiting_input，同一 session_id `142ca65a083a47b6ad569b6d52eae119` 的 intake、diagnose.synthesize、reply.stream、guide.step 四次调用通过 OTLP 写入，Observations API v2 读回确认输入/输出/模型/run_id 与脱敏。离线同链路完整且无 Langfuse 调用。12 项观测层测试 + 76 项模型/取消/API 回归全部通过，ruff 与 diff whitespace 检查通过。部署与验证命令见 [README](../../../../deploy/observability/README.md)。

**范围说明：** 假模型的 44 ms 首可见 / 47 ms 首卡仅证明埋点链路；真实厂商性能、含图 15 秒指标和 A1 多轮完成由 34–36/42 验收。全量后端首次为 324 passed / 24 failed / 2 skipped，失败由同期 34 引入的 step_card / awaiting_input / version 行为变化触发，已在 34 留下回归反馈，未将全量测试标绿。

**口径备注（2026-09-13，来自票 34/35 会话）：** guide 节点在步骤卡就绪时打 `logger=sessions.graph, event=card_ready`（含 card_id、card_ready_ms）；`apply_action(step_feedback)` 打 `event=cp_verify`（feedback / outcome / rule_id / counters）。与运行器侧 `run_metric(card_kind=step_card)` 同口径：都从本 run 的 `at` 到卡片就绪。汇总脚本可两边互校。
