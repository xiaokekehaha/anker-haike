# 运行手册：数据库（PostgreSQL）

整理日期：2026-09-12（票 47）。票 50 的总手册引用本页。

## 1. 单点风险

- PostgreSQL 是系统里**唯一真正的单点**：LangGraph checkpoint（权威业务状态）、session_events / session_actions、products / plans，以及 WeKnora 自身的库都在同一个实例。模型 API 与 WeKnora 各有降级路径，PostgreSQL 没有。
- 演示 / 单机部署不做主从。缓解手段只有两条：每日逻辑备份（保留 7 天）与本页的恢复流程。演示前**手动执行一次 `make db-backup`**（04 §5）。
- 实例挂掉时的表现：`/health` 的 db 为 down 且整体 503；sessions 接口 503 `sessions_unavailable`；WeKnora 检索 unavailable。恢复实例后服务自动重连，正在进行的 run 会在重启 orchestrator 时被标记 `server_restarted`（票 08）。

## 2. 备份

| 项 | 值 |
| --- | --- |
| 执行者 | compose 服务 `pg-backup`（与 postgres 同镜像，保证 pg_dump 版本一致） |
| 频率 | 每 `BACKUP_INTERVAL_S`（默认 86400 s）一轮；容器启动即先跑一轮 |
| 内容 | `haike`（编排服务：checkpoint + 业务表）与 `WeKnora` 两库，`pg_dump -Fc` |
| 位置 | 卷 `pg-backups`，容器内 `/backups/<db>_<UTC 时间>.dump` |
| 保留 | `RETENTION_DAYS`（默认 7）天，每轮结束后清理 |
| 状态 | `/backups/last_success`（时间 + 文件）、`/backups/backup.log`、`docker compose logs pg-backup` |

命令：

```bash
make db-backup          # 立即备份一轮
make db-backup-status   # 最近成功时间、文件、日志尾部
```

判断「备份是否健康」：`last_success` 时间距现在不超过一个周期 + 1 h；日志无 `FAIL`。

## 3. 恢复

```bash
make db-backup-status                              # 选文件
make db-restore FILE=haike_20260912T130501Z.dump   # 停 orchestrator → 断开连接 → pg_restore --clean → 起 orchestrator
```

- 恢复的是整库（含 checkpoint 表与 alembic_version），恢复后不需要再跑迁移；若备份版本早于当前代码，orchestrator 在 dev 会自动 upgrade，非 dev 会拒绝提供 sessions 接口并在日志提示 `make db-upgrade`。
- 恢复 WeKnora 库：`make db-restore FILE=WeKnora_<ts>.dump`，之后重启 weknora-app。知识库文件本体在 `weknora-files` 卷，逻辑备份不包含；知识库变更前的语义快照见 `make kb-snapshot`（`make kb-ingest` 会自动先导出）。
- 恢复期间前端会收到 503 / 断流，按票 08 的恢复态在服务回来后读快照续接。

### 3.1 恢复演练记录（2026-09-12）

在 awaiting_input（等待选产品）的会话上 `make db-backup`（haike 库 dump 约 205 KB）→ 用 psql 删除该会话的 sessions / session_events / session_actions / checkpoints* 全部行（GET 快照 404）→ `make db-restore FILE=haike_<ts>.dump`（约 1 s）→ GET 快照 200，pending_input 与备份时一致 → 用原 card_id / expected_version 发 select_product → run 正常推进到 diagnose，version 4 → 8。恢复过程中服务端连接被断开一次，连接池自动重建，首个请求即成功。

## 4. 迁移

- 业务表结构唯一来源：`orchestrator/migrations/versions/`（Alembic）。各 store 里残留的 `create table if not exists` 只是幂等兜底，**新增 / 修改列必须走迁移**。
- LangGraph checkpoint 表由框架 `AsyncPostgresSaver.setup()` 自管（有自己的 `checkpoint_migrations`），不进 Alembic。
- 启动期：`APP_ENV=dev` 落后自动升级；其他环境落后 → sessions 接口 503，日志 `run make db-upgrade`。

```bash
make db-upgrade      # 空库一条命令建齐 / 升级到 head
make db-current      # 库内版本 vs 代码 head
make db-check        # CI：不一致非零退出
make db-revision MSG="add session_images"
```

## 5. 常见问题

| 现象 | 处置 |
| --- | --- |
| `/health` db down | `docker compose ps postgres`；`docker compose logs postgres --tail 50`；磁盘满看 `docker system df` |
| 启动日志 `database schema at ... code expects ...` | `make db-upgrade`（非 dev 环境需人工确认后执行） |
| `make db-restore` 报 `database is being accessed by other users` | 还有连接未断：`docker compose stop orchestrator weknora-app` 后重试 |
| 备份日志 `FAIL db=...` | 多为口令 / 网络；`docker compose exec pg-backup pg_isready`；检查 `.env` 的 DB_PASSWORD |
| 需要回到某个知识库版本 | `make kb-snapshot DIR=data/knowledge/snapshots/<ts>` |

## 6. 数据保留与按会话删除（票 48）

分类 TTL（07 §12）：图片 1 小时（`session_images`，images.runtime 每 5 分钟清）；会话状态 24 小时（`sessions` 投影 + `session_events` + `session_actions` + `session_images` + LangGraph `checkpoints` / `checkpoint_blobs` / `checkpoint_writes`，以 `sessions.updated_at` 判定，有 active run 的不删，无投影行的孤儿事件按最后事件时间清）；检索追踪 7 天（随 checkpoint 过期；`logs/events.jsonl.N` 轮转备份超 7 天删除）。清理循环在编排服务进程内（默认每 10 分钟），每轮写结构化日志 `event=retention_purge`，带各表删除行数。

| 操作 | 命令 | 说明 |
| --- | --- | --- |
| 看当前 TTL | `cd orchestrator && uv run --env-file ../.env haike-retention ttl` | 由 `RETENTION_SESSION_HOURS` / `RETENTION_TRACE_DAYS` 覆盖 |
| 手动清理一轮 | `make retention-purge [HOURS=24]` | 打印 `{sessions, orphan_sessions, deleted, log_backups_removed}` |
| 删除某会话全部数据 | `make session-delete SID=<session_id>` | 退出码 1 表示本来就没有数据 |
| HTTP 删除（人工处理删除请求） | `curl -X DELETE -H "X-Admin-Token: $ADMIN_TOKEN" https://<host>/sessions/<id>` | `ADMIN_TOKEN` 未配置时 403 `admin_disabled`；有 active run 先取消；成功返回各表行数，之后快照 / 图片 / 事件续接均 404 |

排查：日志里搜 `retention_purge` 看每轮统计；`retention purge failed` 为异常（下一轮继续）；删除后想确认无残留可跑 `select count(*) from session_events where session_id = '<id>'` 等（表清单见 `orchestrator/app/retention.py: SESSION_TABLES`）。脱敏：JSONL 与 Langfuse 共用 `app/observability/privacy.py`，手机号 / 订单号 / 地址 / 长数字串在写出前替换为 `[REDACTED]`；核对方法见 `tests/test_retention.py::test_jsonl_has_no_plaintext_phone_order_or_address`。

