# 15: 规则服务骨架与 CP-in 安全升级

**What to build:** 自研规则服务提供带编号的规则判定；安全词字典（冒烟、烧焦味、电池鼓包等）配置化；CP-in 在每条用户文本进入图之后、任何模型调用之前运行，命中 R4 或明确要求人工（R3）写入 safety_flags 并直接跳到 escalate。

**Blocked by:** 05（会话创建与 SSE 基础流）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（2026-09-12 认领；改动范围 `orchestrator/app/rules/`、`config/rules/`；图内 CP-in 节点以追加方式接入 `app/sessions/graph.py`（与 A 协调，只加节点与状态字段，不改现有节点语义））

- [x] 安全词字典为配置文件，热加载或重启生效（`config/rules/safety_terms.yaml`，R3 / R4 / R6 带编号与优先级；`RulesService` 每次判定前按 mtime 热加载，改坏文件时保留旧字典并记 error）
- [x] 首句含安全词时不发生任何模型调用（用假 router 断言）（CP-in 在 intake 节点末尾、任何模型调用之前；命中即条件边跳 escalate 节点，progress 序列为 intake → escalate，reply 及后续节点不执行；测试挂载一调用即失败的假 router 并断言零调用）
- [x] safety_flags 含 rule_id / source / ts（另含 term；source ∈ text / observation / action / action_note；写入图状态 `safety_flags` 跨 run 累积，`escalate_reason` 记触发规则）
- [x] 规则判定结果带规则编号写入结构化日志（logger `rules`，extra 含 event=rule_hit / checkpoint / rule_id / source / term / action / session_id / rules_version）

**设计依据：** 09 §1；03 §1.7

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/rules/service.py`（字典模型、`check_in(text, observations, action_kind, action_note)`、CP-pre-step / CP-verify 接口预留给票 25 / 33 / 36）；`app/sessions/graph.py` 追加：状态字段 `safety_flags` / `escalate_reason`、intake 末尾 CP-in、`route_after_intake` 条件边、`escalate` 占位节点（摘要卡在票 16）。非安全路径节点数不变，票 05 / 07 既有测试不受影响。tests/test_rules.py 17 项。
