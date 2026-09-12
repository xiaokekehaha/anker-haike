# 发现
- 现有模型有 attempts/usage，但 invoke/stream 无追踪；runner Emitter 是全量业务事件的集中落点。
- Langfuse 官方 Compose 当前版本为 v4，含 ClickHouse/Redis/对象存储等依赖；需显式固定并仅在 observability profile 启用。
- https://langfuse.com/self-hosting/deployment/docker-compose 为官方部署来源。

- v4 默认 events_only 已拒收 legacy trace-create/generation-create；HTTP 207 不能当作写入成功。官方说明：https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4 。
- 最终采用 OTLP HTTP/JSON，generation 根 span 每次模型调用一条，langfuse.session.id 在每条 span 携带；run_id/lane/attempts 为显式 observation metadata。官方映射：https://langfuse.com/integrations/native/opentelemetry 。
- 读回改用 /api/public/v2/observations，以 sessionId filter 查询并请求 io/metadata/model/usage；https://langfuse.com/docs/api-and-data-platform/features/observations-api 。
- 本地 JSONL 和远端导出共享递归脱敏，支持 JSON 文本内的字母数字订单号；不会对业务返回做脱敏或修改。未知 token 省略而非伪填零。
- 统计采用最近秩百分位，按 session/run 去重；缺失首可见/首卡不当成零延迟。
