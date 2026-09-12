# 本机可选 Langfuse

票 44 的部署部分。版本固定为 Langfuse 4.35.0，仅监听本机 `127.0.0.1:3000`；Postgres、Redis、ClickHouse 和对象存储使用本项目独立服务与数据卷，不共享业务数据库。

依据：[官方 Compose](https://github.com/langfuse/langfuse/blob/main/docker-compose.yml)、[自托管指南](https://langfuse.com/self-hosting/deployment/docker-compose)。MinIO 使用官方 Compose 推荐的 Chainguard 镜像，并以拉取到的 digest 冻结。

从仓库根目录运行：

```sh
python3 deploy/observability/init.py
docker compose --env-file .env --env-file deploy/observability/.env -f docker-compose.yml -f deploy/observability/compose.yaml --profile observability up -d langfuse-web langfuse-worker
```

初始化脚本不覆盖已有凭据，文件权限为 0600，已由 `.gitignore` 排除。UI 登录账号为 `admin@haike.local`，口令在 `deploy/observability/.env` 的 `OBS_USER_PASSWORD`；不要把凭据复制到票据、日志或提交。

开发环境启用追踪时加载该文件中的 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`，并设置 `LANGFUSE_ENABLED=true`、`LANGFUSE_BASE_URL=http://localhost:3000`。容器内地址为 `http://langfuse-web:3000`。此文件不改变默认模型厂商，也不会替你重启编排服务。关闭追踪使用 `LANGFUSE_ENABLED=false`。

查看状态与关闭本次新增服务：

```sh
docker compose --env-file .env --env-file deploy/observability/.env -f docker-compose.yml -f deploy/observability/compose.yaml --profile observability ps langfuse-web langfuse-worker obs-postgres obs-redis obs-clickhouse obs-minio
docker compose --env-file .env --env-file deploy/observability/.env -f docker-compose.yml -f deploy/observability/compose.yaml --profile observability stop langfuse-web langfuse-worker obs-postgres obs-redis obs-clickhouse obs-minio
```

不使用整个项目的 `down -v`，避免删除业务数据或其他会话的服务。追踪依赖服务会占用额外内存和磁盘，默认关闭；启动与联调结果见本票 planning 记录。

## 验证与统计

从仓库根目录运行：

```sh
uv run --project orchestrator python deploy/observability/smoke.py
uv run --project orchestrator python deploy/observability/smoke.py --offline
uv run --project orchestrator haike-metrics logs/observability-smoke-session.jsonl --out logs/observability-metrics.json
```

联调使用内存会话、脚本化假模型和假知识库，执行 A1 首轮直到步骤卡等待反馈，验证 intake、diagnose.synthesize、reply.stream、guide.step 四次调用按同一个 session_id / run_id 关联。在线模式真实写入本机 Langfuse，再通过 API 读回输入、输出、模型、token 和关联信息，验证手机号/订单号脱敏。离线模式不读取 Langfuse 凭据、不连接该服务，同样验证业务事件与 JSONL。结果在 `logs/observability-smoke-result.json`、`logs/observability-offline-result.json`，最新单会话 JSONL 在 `logs/observability-smoke-session.jsonl`。

应用追踪使用 [OTLP HTTP/JSON](https://langfuse.com/integrations/native/opentelemetry) `/api/public/otel/v1/traces`，带 `x-langfuse-ingestion-version: 4`；读取使用 [Observations API v2](https://langfuse.com/docs/api-and-data-platform/features/observations-api)。保持 v4 默认 `events_only`，不依赖旧 ingestion / traces API 或迁移兼容模式。UI 进入 Haike service 项目的 Observations，用 Session ID 筛选对应运行。

每次 ModelRouter 调用保留输入、输出、model_used、attempts、耗时与厂商提供的 token；没有返回 token 时不伪填零。日志统一递归脱敏，图片内容省略；包括状态迁移、检索、规则命中和运行指标。导出队列最多 100 项，满时丢追踪并记录计数；连接失败、部分拒收不阻止业务执行，退出最多等待队列 3 秒。文件日志每份 10 MB，保留 3 份轮转，写文件不可用时退回 stderr JSON。

`first_visible_ms` 从 run 开始计至首个非空 message；`card_ready_ms` 计至首个 product_card / receipt_card / step_card。每个 run 各计一次，CLI 按 session_id / run_id 去重，输出最近秩 P50 / P95 和逐会话明细；缺失指标保留 null，不补零。假模型联调的毫秒数仅用于验证埋点和统计链路，不代表真实模型或生产 SLO。
