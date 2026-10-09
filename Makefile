.DEFAULT_GOAL := help
COMPOSE ?= docker compose

help: ## 列出命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

## ---- 容器 ----
up: ## 构建并拉起全部容器（含 WeKnora 网页 8081）
	$(COMPOSE) --profile ui up -d --build
down: ## 停止容器，保留数据
	$(COMPOSE) --profile ui down
reset: ## 停止容器并删除全部数据卷（需二次确认）
	@read -p "将删除 postgres / redis / weknora 全部数据，继续? [y/N] " a && [ "$$a" = "y" ] && $(COMPOSE) --profile ui down -v
logs: ## 跟随日志
	$(COMPOSE) logs -f --tail=100
ps: ## 容器状态
	$(COMPOSE) ps
restart-api: ## 重启业务编排服务，使进程内知识索引重新加载
	$(COMPOSE) restart orchestrator
health: ## 打印编排服务聚合健康
	@curl -fsS http://localhost:$${ORCHESTRATOR_PORT:-8000}/health | python3 -m json.tool

## ---- 本机开发 ----
dev-sync: ## 安装后端依赖（uv）
	cd orchestrator && uv sync
dev-api: ## 本机起编排服务（读根目录 .env）
	cd orchestrator && uv run --env-file ../.env uvicorn app.main:app --reload --port $${PORT:-8000}
test: ## 后端单元测试
	cd orchestrator && uv run pytest -q
lint: ## ruff 检查
	cd orchestrator && uv run ruff check .

## ---- 模型层（票 09）----
route-table: ## 从 config/models.yaml 生成路由展示表（LANE=domestic|overseas）
	cd orchestrator && uv run --env-file ../.env haike-route-table $(if $(LANE),--lane $(LANE),)
model-probe: ## 对 task 发一次最简调用：make model-probe TASK=intake [ALIAS=deepseek]
	cd orchestrator && uv run --env-file ../.env haike-model-probe $(or $(TASK),intake) $(if $(ALIAS),--alias $(ALIAS),)
bakeoff: ## bake-off 评测（票 42）：make bakeoff [TASK=intake] [ALIAS=deepseek] [EXTRA=deepseek-pro] [REPEATS=3]；报告在 reports/bakeoff/
	cd orchestrator && uv run --env-file ../.env haike-bakeoff $(if $(TASK),--task $(TASK),) $(if $(ALIAS),--alias $(ALIAS),) $(if $(REPEATS),--repeats $(REPEATS),) $(if $(EXTRA),--extra $(EXTRA),)
	cd contracts && uv run --group dev ruff check .

.PHONY: contracts contracts-check contracts-test
## ---- 参考数据（票 19 / 31）----
seed: ## 写入 products 参考数据到 PostgreSQL（幂等）：make seed [WHAT=products|all]
	cd orchestrator && uv run --env-file ../.env haike-seed $(or $(WHAT),all)
plans-schema: ## 输出排障计划 JSON Schema（计划由官方 Q&A 生成；--enum 收窄 plan_id）
	cd orchestrator && uv run haike-plans-schema --enum

## ---- 知识库（票 26）----
kb-bootstrap: ## 在本机 WeKnora 自助注册项目独立 tenant，并把 API key 写入 .env
	cd orchestrator && uv run --env-file ../.env haike-kb bootstrap
kb-ingest: ## 官方 Q&A 幂等导入 haike_kb_qa（一条 Q&A 一个知识），删除旧中文手册 / FAQ / 合成工单库，写 manifest；结束后重建 BM25 索引
	cd orchestrator && uv run --env-file ../.env haike-kb ingest $(if $(KEEP_LEGACY),--keep-legacy,)
	@# WeKnora v0.8.0 + ParadeDB：批量删除知识后 bm25 索引会残留失效行指针（item_pointer_is_valid 断言），关键词检索 500；重建即恢复
	$(COMPOSE) exec -T postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$${POSTGRES_DB:-WeKnora}" -c "REINDEX INDEX embeddings_search_idx;"'

kb-eval: ## 检索评测：63 单工单首封打 kb_qa，按语言统计 recall@5 → reports/retrieval/（ARM= 报告标签）
	cd orchestrator && uv run --env-file ../.env haike-kb eval --arm $(or $(ARM),A)
kb-verify: ## 打印各知识库解析状态与 custom_metadata
	cd orchestrator && uv run --env-file ../.env haike-kb verify

## ---- 回放（票 43）----
replay-record: ## 真实模型 + WeKnora 跑内置脚本并录制：make replay-record CASE=t55_main [SCENARIO=t55_main]
	cd orchestrator && uv run --env-file ../.env haike-replay record $(CASE) $(if $(SCENARIO),--scenario $(SCENARIO),)
replay-verify: ## 断网重放录制包并核对（未命中 / 缺事件非零退出）：make replay-verify CASE=t55_main
	cd orchestrator && uv run --env-file ../.env haike-replay verify $(CASE)
replay-check: ## 录制包清单与当前 prompt / models / kb / rules 版本比对：make replay-check CASE=t55_main
	cd orchestrator && uv run --env-file ../.env haike-replay check $(CASE)
replay-list: ## 列出录制包
	cd orchestrator && uv run --env-file ../.env haike-replay list
replay-all: ## 顺序核对全部演示回放包，缺包或失败时非零退出
	cd orchestrator && uv run --env-file ../.env haike-replay verify-all

## ---- 契约（票 03 / 04）----
contracts: ## 由 Pydantic 导出 Schema，并生成前端类型与 Zod 校验器
	cd contracts && uv run haike-contracts-export
	npm --prefix frontend run contracts:generate
contracts-check: ## 校验已提交的 Schema 与模型一致（CI 用，漂移则非零退出）
	cd contracts && uv run haike-contracts-export --check
	npm --prefix frontend run contracts:check
contracts-test: ## 契约单测（样例校验、导出稳定性）
	cd contracts && uv run pytest -q

## ---- 会话（票 07）----
sessions-rebuild: ## 从事件日志 + checkpoint 重建 sessions 投影表：make sessions-rebuild ARGS="--all"
	cd orchestrator && uv run --env-file ../.env haike-sessions-rebuild $(ARGS)

## ---- 数据库运维（票 47）----
db-upgrade: ## 业务表迁移到最新版本（空库一条命令建齐；LangGraph checkpoint 表由服务启动时自建）
	cd orchestrator && uv run --env-file ../.env haike-db upgrade
db-current: ## 打印库内迁移版本与代码 head
	cd orchestrator && uv run --env-file ../.env haike-db current
db-check: ## 版本不一致时非零退出（CI / 上线前）
	cd orchestrator && uv run --env-file ../.env haike-db check
db-revision: ## 新建一条空迁移：make db-revision MSG="add session_images"
	cd orchestrator && uv run alembic -c alembic.ini revision -m "$(MSG)"
inspect: ## 故障与边界场景巡检（票 45）：stub 模型一条命令跑完并回填 findings.md；make inspect LIVE=http://127.0.0.1:8000 追加真实 A1 样例
	cd orchestrator && uv run --env-file ../.env haike-inspect $(if $(LIVE),--live $(LIVE),) $(if $(GROUP),--group $(GROUP),)

## ---- 管理员观测台（docs/planning/2026-09-13_admin-observability-console）----
analytics-backfill: ## 把历史会话补成观测台事实（幂等，可反复跑）：make analytics-backfill [SINCE=2026-09-01] [DRY=1]
	cd orchestrator && uv run --env-file ../.env haike-analytics backfill $(if $(SINCE),--since $(SINCE),) $(if $(DRY),--dry-run,)
analytics-stats: ## 打印各事实表行数与结果分布
	cd orchestrator && uv run --env-file ../.env haike-analytics stats

retention-purge: ## 按分类 TTL 清理一轮（会话 24 h / 追踪 7 d）并打印统计：make retention-purge [HOURS=24]
	cd orchestrator && uv run --env-file ../.env haike-retention purge $(if $(HOURS),--session-hours $(HOURS),)

session-delete: ## 删除某会话全部数据（投影 / 事件 / 动作 / 图片 / checkpoint）：make session-delete SID=<session_id>
	cd orchestrator && uv run --env-file ../.env haike-retention delete $(SID)

db-backup: ## 立即备份 haike + WeKnora 两库到 pg-backups 卷
	$(COMPOSE) exec pg-backup /opt/backup/backup.sh once
db-backup-status: ## 最近一次成功备份时间、文件列表与日志尾部
	@$(COMPOSE) exec pg-backup sh -c 'echo "last_success:"; cat /backups/last_success 2>/dev/null || echo "(none)"; echo; ls -lh /backups/*.dump 2>/dev/null; echo; tail -n 5 /backups/backup.log 2>/dev/null'
db-restore: ## 恢复：make db-restore FILE=haike_20260912T120000Z.dump（停编排服务 → 断开连接 → pg_restore → 起服务）
	@test -n "$(FILE)" || (echo "FILE= 必填，见 make db-backup-status" && exit 2)
	$(COMPOSE) stop orchestrator
	$(COMPOSE) exec pg-backup /opt/backup/restore.sh $(FILE)
	$(COMPOSE) start orchestrator

## ---- 发布 / 回滚 / CI（票 49）----
release: ## 生成 RELEASE.md 并快照 config/ 到 releases/<id>/：make release [REL=20260912-abc1234]
	scripts/release.sh $(REL)
release-check: ## 校验 RELEASE.md 声明的版本与仓库现状一致（漂移非零退出）
	scripts/release-check.sh
rollback: ## 切回某版 config/ 并重启编排服务，等健康检查：make rollback REL=<release_id>
	scripts/rollback.sh $(REL)
ci-local: ## 本机复现 CI 全部检查（ruff / db-check / pytest / contracts / 前端）
	scripts/ci-local.sh

## ---- 线上 / 对外演示（票 46）----
HAIKE_ENV_FILE ?= /etc/haike/haike.env
COMPOSE_PROD = $(COMPOSE) --env-file $(HAIKE_ENV_FILE) -f docker-compose.yml -f deploy/prod/docker-compose.prod.yml
proxy-cert: ## 自签证书：make proxy-cert HOST=demo.example.com
	scripts/proxy-cert.sh $(HOST)
proxy-passwd: ## 基础认证账号：make proxy-passwd USER=judge [PASS=...]
	scripts/proxy-passwd.sh $(USER) $(PASS)
prod-up: ## 以仓库外密钥文件 + HTTPS 代理拉起（只暴露 80/443）
	$(COMPOSE_PROD) up -d --build
prod-down: ## 停止线上编排
	$(COMPOSE_PROD) down
scan-secrets: ## 扫描仓库与镜像中的密钥：make scan-secrets [IMAGE=haike/orchestrator:dev]
	scripts/scan-secrets.sh $(IMAGE)
