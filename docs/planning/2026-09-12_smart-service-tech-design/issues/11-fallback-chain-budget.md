# 11: 降级链与 task 预算

**What to build:** invoke 在超时 / 429 / 5xx 时同模型重试一次，再跳下一家，链上最多三家，总耗时不超过 budget_ms；拒答不重试直接跳；能力不匹配在路由前跳过。用可注入故障的假 provider 验证全部分支。

**Blocked by:** 10（结构化 invoke：三种输出策略与 Pydantic 校验）

**Status:** ready-for-agent

- [ ] 假 provider 可按序注入超时、429、拒答、schema 错误，attempts 记录与预期一致
- [ ] 预算耗尽立即停止并返回最后错误，不尝试剩余模型
- [ ] 厂商 SDK max_retries=0（配置断言测试）
- [ ] 跨通道降级（国内链尾接 overseas 别名）可触发并在 attempts 标注 lane

**设计依据：** model-selection §3.6；08 §8
