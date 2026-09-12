# 47: 生产就绪：数据库迁移与备份恢复

**What to build:** 业务表用 Alembic 管理迁移，启动时校验版本；PostgreSQL 每日自动备份并保留 7 天；提供一键恢复脚本并演练一次恢复后会话可继续。WeKnora 知识库变更前自动导出快照。

**Blocked by:** 07（快照接口与 sessions 投影表）

**Status:** done（2026-09-12）

**Owner:** Claude Code A（2026-09-12 认领；`orchestrator/migrations/`、`orchestrator/app/db/`、`deploy/backup/`、docker-compose 备份服务、Makefile 追加目标、`docs/runbook/`；不改 app/sessions 业务逻辑与 B 的 store）

- [x] 从空库到当前版本一条迁移命令完成（`make db-upgrade` → Alembic 基线 0001；实测临时空库 haike_fresh 一条命令建齐 7 张表；对迁移引入前已建好的库幂等「收编」）
- [x] 备份任务有日志与最近成功时间可查（compose 服务 pg-backup 每日一轮、保留 7 天；`/backups/last_success`、`/backups/backup.log`、`make db-backup-status`）
- [x] 恢复演练后已有会话快照可读、可续接（实测：等待卡片的会话 → 备份 → 删除其会话行 / 事件 / 动作 / checkpoint（GET 404）→ `make db-restore` → 快照带原 pending_input、http 200 → 用原 card_id / version 发 select_product → 推进到 diagnose、version 8）
- [x] PostgreSQL 单点风险在运行手册中列明（docs/runbook/database.md §1；README 增「数据库运维」入口）

**设计依据：** 04 §4、§5；03 §3.1

**实现记录（2026-09-12，Claude Code A）：** `orchestrator/alembic.ini` + `migrations/`（env.py 从 app.settings 取 URL，psycopg3 方言；`versions/0001_baseline.py` 用 IF NOT EXISTS 覆盖 sessions / session_events / session_actions / products / catalog_meta / plans）；`app/db/migrations.py`（head / current / upgrade / ensure_schema：dev 自动升级、其他环境落后抛 SchemaOutOfDate → sessions 接口 503 并提示 `make db-upgrade`）、`app/db/cli.py`（haike-db upgrade / current / check）；runtime 启动期先校验再 setup，连接池加 `check=check_connection`。`deploy/backup/backup.sh`（loop / once，pg_dump -Fc，last_success，按天清理）、`restore.sh`（断连 → pg_restore --clean → 属主改回目标库属主）、compose 服务 `pg-backup`（与 postgres 同镜像）、卷 `pg-backups`；Makefile 追加 db-upgrade / db-current / db-check / db-revision / db-backup / db-backup-status / db-restore，以及 `kb-ingest: kb-snapshot-export` 前置（知识库变更前自动导出快照）。测试 tests/test_db_migrations.py 6 项（基线覆盖全部 store DDL、URL 方言、prod 落后抛错、dev 自动升级、真实库 current==head）。

**演练中抓到并修掉的两个问题：** ① dump 不带 owner、pg_restore 以超级用户执行 → 恢复出的表归 postgres，应用账号 haike `permission denied`；restore.sh 现在恢复后把 public 下全部表 / 序列 / 视图属主改回目标库属主。② 恢复时 pg_terminate_backend 杀掉服务端已建连接，恢复后第一个请求拿到坏连接报 AdminShutdown；连接池加借出前检查后首个请求直接 200。

**边界：** LangGraph checkpoint 表由 AsyncPostgresSaver.setup() 自管（框架有自己的 checkpoint_migrations），不进 Alembic；备份是整库逻辑备份，天然包含。B 的 catalog / plans store 仍保留幂等 DDL 作兜底，结构变更必须走迁移（运行手册 §4 已写明）。WeKnora 文件卷（weknora-files）不在逻辑备份内。
