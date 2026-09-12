# 44: 可观测：Langfuse profile 与延迟指标

**What to build:** Langfuse 作为 compose 可选 profile；ModelRouter 每次调用写 Langfuse（输入、输出、延迟、token、model_used、attempts）；状态迁移、检索、规则判定写结构化 JSONL；埋点 first_visible_ms 与 card_ready_ms 并可按会话汇总；关闭 Langfuse 时只写日志。

**Blocked by:** 12（限流退避与全局有界队列）、28（tool_call 与 evidence 事件 + EvidenceDrawer）

**Status:** ready-for-agent

- [ ] 开启 profile 后一次 A1 会话在 Langfuse 中按 session_id 串联全部调用
- [ ] 关闭 profile 时无报错且结构化日志完整
- [ ] 有脚本从日志汇总 first_visible_ms / card_ready_ms P50 / P95
- [ ] 日志中手机号与订单号脱敏

**设计依据：** 04 §3；07 §15
