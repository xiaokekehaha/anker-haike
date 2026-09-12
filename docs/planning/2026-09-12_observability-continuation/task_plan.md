# 票 44 可观测接续
## Goal
实现本地结构化日志与脱敏、ModelRouter 调用追踪、run 首可见/卡片延迟、汇总 CLI 和可选 Langfuse Compose。
### Phase 1: 边界与官方接口核对
**Status:** complete
### Phase 2: 日志、追踪与统计
**Status:** complete
### Phase 3: 可选部署、验证与票据回填
**Status:** complete
## Decisions
- 凭证前端由正在修改同文件的会话继续；本轮改认领 44。Claude C 随后让出重复实现，由 Codex 统一完成。
- 追踪故障不阻塞模型或会话，发送前统一脱敏；关闭 Langfuse 仍保留 JSONL。
- 使用 v4 默认 events_only 与 OTLP HTTP/JSON，新版 Observations API 查询；不引入 legacy/dual 迁移模式。
- 保留配置链最多 3 项，修正 guide.step 超限；修复上轮三处 lint。
## Errors Encountered
- 旧 Docker Hub MinIO 镜像不存在：按官方 Compose 切至 Chainguard 固定 digest。
- Web 只绑定容器 hostname 导致 localhost 健康检查失败：设置 HOSTNAME=0.0.0.0，仅主机 loopback 暴露端口。
- 旧 ingestion 返回 207 但内部 400，旧 traces 查询 404：查官方 v4 迁移指南，改为 OTLP / v2 observations，真实读回成功。
- 全量后端 24 条旧断言不适配同期 34 新 guide 流程：反馈给现有 owner，未并行修改业务测试。
## Completion
- 票 44 done；观测层 12 / 12，相关模型/取消/API 76 / 76；在线和离线 smoke、指标 CLI、ruff、diff whitespace 检查通过。
- 未提交、未重启现有业务容器。只启动本票可选本机 Langfuse 及其独立依赖。
