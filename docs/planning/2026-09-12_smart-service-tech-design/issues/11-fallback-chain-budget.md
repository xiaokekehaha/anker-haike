# 11: 降级链与 task 预算

**What to build:** invoke 在超时 / 429 / 5xx 时同模型重试一次，再跳下一家，链上最多三家，总耗时不超过 budget_ms；拒答不重试直接跳；能力不匹配在路由前跳过。用可注入故障的假 provider 验证全部分支。

**Blocked by:** 10（结构化 invoke：三种输出策略与 Pydantic 校验）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线）

- [x] 假 provider 可按序注入超时、429、拒答、schema 错误，attempts 记录与预期一致（`app/models/fake.py` 脚本项支持异常 / AIMessage(stop_reason=refusal) / 文本；tests/test_models_fallback.py 13 项覆盖 timeout→同模型重试、429×2→换家、5xx 重试、拒答不重试、schema+timeout 混合、整链失败 6 次 attempts）
- [x] 预算耗尽立即停止并返回最后错误，不尝试剩余模型（单次超时 = min(模型 timeout_s, 剩余)；退避后剩余不足 1 s 即抛 `ModelInvokeError(reason=budget exhausted)`，注入时钟验证后续模型零调用）
- [x] 厂商 SDK max_retries=0（配置断言测试）（仓库 models.yaml `retry.sdk_max_retries=0` 且 ChatOpenAI / ChatAnthropic 实例 `max_retries == 0`）
- [x] 跨通道降级（国内链尾接 overseas 别名）可触发并在 attempts 标注 lane（attempts[].lane 取厂商 `lane`，测试断言末次为 overseas）

**设计依据：** model-selection §3.6；08 §8

**实现记录（2026-09-12，Claude Code B）：** `app/models/router.py`：`classify_exception`（TimeoutError / SDK Timeout → timeout；429 / RateLimit / ResourceExhausted → rate_limited；5xx / InternalServerError / APIConnectionError → server_error；content_filter / data_inspection_failed / refusal → refusal；其余 error）、`detect_refusal`（stop_reason / finish_reason ∈ {refusal, content_filter}）、`backoff_seconds`（1 s + [0, 0.5) 抖动；429 按 1 / 2 / 4 s，票 12 复用）、能力跳过（route.needs_vision 或消息含图片而模型 `vision: false` → skipped，不计入重试）；`clock` / `sleep` / `rng` 可注入。同模型重试次数由 `retry.same_model_max` 控制，链上家数由 `retry.chain_max` 截断。
