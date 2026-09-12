# 15: 规则服务骨架与 CP-in 安全升级

**What to build:** 自研规则服务提供带编号的规则判定；安全词字典（冒烟、烧焦味、电池鼓包等）配置化；CP-in 在每条用户文本进入图之后、任何模型调用之前运行，命中 R4 或明确要求人工（R3）写入 safety_flags 并直接跳到 escalate。

**Blocked by:** 05（会话创建与 SSE 基础流）

**Status:** ready-for-agent

- [ ] 安全词字典为配置文件，热加载或重启生效
- [ ] 首句含安全词时不发生任何模型调用（用假 router 断言）
- [ ] safety_flags 含 rule_id / source / ts
- [ ] 规则判定结果带规则编号写入结构化日志

**设计依据：** 09 §1；03 §1.7
