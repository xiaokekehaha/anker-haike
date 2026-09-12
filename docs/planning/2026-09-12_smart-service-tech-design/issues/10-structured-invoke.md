# 10: 结构化 invoke：三种输出策略与 Pydantic 校验

**What to build:** ModelRouter.invoke 接受 task、消息与 Pydantic Schema，按模型能力选原生 json_schema / json_object 加 schema 提示 / 工具调用三种方法，统一 Pydantic 校验；校验失败带错误重试一次。返回 parsed、model_used、lane、latency、usage、attempts。

**Blocked by:** 09（models.yaml 加载、校验与别名路由）

**Status:** claimed

**Owner:** Claude Code B（模型层线，2026-09-12 认领，排队，票 09 后）

- [ ] 三种策略各有一个模型走通并通过同一 Schema 校验；json_object 策略以 DeepSeek（默认测试 key）为验证模型
- [ ] 校验失败时第二次请求包含错误提示，再失败抛出带 attempts 的异常
- [ ] 所有 invoke 调用 tag=internal，metadata 含 task / session_id / lane
- [ ] Claude 走 effort 参数，其他厂商走 temperature 映射（单元测试覆盖映射表）

**设计依据：** model-selection §3.5；03 §2.4
