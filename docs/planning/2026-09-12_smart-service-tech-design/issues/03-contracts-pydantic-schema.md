# 03: contracts 包：事件 / 动作 / 快照 Pydantic 模型与 JSON Schema

**What to build:** 按会话执行契约定义全部事件类型、动作请求、快照响应的 Pydantic 模型，并提供一条命令导出三份 JSON Schema。后端流式接口和前端类型都以此为唯一来源。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** ready-for-agent

- [ ] 事件模型覆盖契约 §5 全部 15 种 type，字段与层级（step 对象、summary 对象）一致
- [ ] 动作模型覆盖 6 种 kind 及各自 payload；快照模型含 active_run / pending_input / timeline / last_error / cancelled_run
- [ ] 一条 make 命令生成三份 Schema 文件，重复执行结果稳定
- [ ] 对每种事件至少一条合法样例通过校验，一条非法样例被拒绝

**设计依据：** 08 §4–§6、§9
