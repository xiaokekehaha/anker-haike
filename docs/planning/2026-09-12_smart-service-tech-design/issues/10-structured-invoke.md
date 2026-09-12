# 10: 结构化 invoke：三种输出策略与 Pydantic 校验

**What to build:** ModelRouter.invoke 接受 task、消息与 Pydantic Schema，按模型能力选原生 json_schema / json_object 加 schema 提示 / 工具调用三种方法，统一 Pydantic 校验；校验失败带错误重试一次。返回 parsed、model_used、lane、latency、usage、attempts。

**Blocked by:** 09（models.yaml 加载、校验与别名路由）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线）

- [x] 三种策略各有一个模型走通并通过同一 Schema 校验；json_object 策略以 DeepSeek（默认测试 key）为验证模型（单测：三种策略用同一 Emotion schema；真实：DeepSeek json_object 1.3 s / tools 1.3 s 均解析出同一结果；DeepSeek 不支持 json_schema（400 `response_format type is unavailable`），router 记为 error 后换下一家，符合配置 `structured: json_object`）
- [x] 校验失败时第二次请求包含错误提示，再失败抛出带 attempts 的异常（HumanMessage「上一次输出未通过校验：…」；链耗尽抛 `ModelInvokeError(task, attempts)`）
- [x] 所有 invoke 调用 tag=internal，metadata 含 task / session_id / lane（另含 alias / method；假模型从 run_manager 读回断言）
- [x] Claude 走 effort 参数，其他厂商走 temperature 映射（`provider_params`：anthropic → `output_config.effort`；其余 low/medium/high → 0 / 0.2 / 0.3；tests/test_models_registry.py）

**设计依据：** model-selection §3.5；03 §2.4

**实现记录（2026-09-12，Claude Code B）：** `app/models/router.py`（`ModelRouter.invoke`：按 `structured` 选 json_schema / json_object + schema 提示 / tools；统一 Pydantic 校验；`method=` 可强制策略；返回 `ModelResult{parsed, model_used, alias, lane, method, latency_ms, usage, attempts}`）；`app/models/fake.py` 可脚本化假模型（票 11 故障注入复用）；`tests/test_models_router.py` 9 项。本票已含最简链遍历（不可用别名 skipped、传输异常 error 后换下一家、预算耗尽即停），超时 / 429 / 5xx / 拒答的同模型重试与退避在票 11。
