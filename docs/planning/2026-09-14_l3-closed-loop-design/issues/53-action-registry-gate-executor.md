# 53: 动作注册表、授权门与执行器

**What to build:** `config/actions.yaml`（`logistics.query / warranty.check / replacement.create`）与 `app/actions/registry.py` 加载校验（write 必有 requires + idempotency；`from_state` 白名单）；`gate.py` 四项检查输出 `GateResult{passed, checks[], fallback}`；`executor.py`：`action_executions` 表（迁移 0006）、唯一 idempotency_key、running/succeeded/failed/stale 状态、超时、异常分类到用户可见文案、`tool_call` 事件、审计字段（gate_result / policy_version / actions_version）、`privacy.sanitize` 补 tracking_no / service_order_no；`receipts.py` 回执模型与摘要渲染；`params.py` 订单号 / 单号正则抽取 + 缺参列表。

**Blocked by:** 52

**Status:** done

**Owner:** —

- [ ] registry 负例：write 缺 requires 报 ConfigError；未注册 kind 拒绝执行
- [ ] gate 四项各一负例 + 全通过正例；checks 明细可序列化进摘要
- [ ] executor 幂等：同键二次调用返回同回执且后端只调一次；running 超时标 stale 后重试一次
- [ ] 故障注入三模式对应文案与 recoverable 标记；日志无明文单号

**设计依据：** 03 §2–§4、§8；06 §5
