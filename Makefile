.DEFAULT_GOAL := help
COMPOSE ?= docker compose

help: ## 列出命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

## ---- 容器 ----
up: ## 构建并拉起全部容器
	$(COMPOSE) up -d --build
down: ## 停止容器，保留数据
	$(COMPOSE) down
reset: ## 停止容器并删除全部数据卷（需二次确认）
	@read -p "将删除 postgres / redis / weknora 全部数据，继续? [y/N] " a && [ "$$a" = "y" ] && $(COMPOSE) down -v
logs: ## 跟随日志
	$(COMPOSE) logs -f --tail=100
ps: ## 容器状态
	$(COMPOSE) ps
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
	cd contracts && uv run --group dev ruff check .

.PHONY: contracts contracts-check contracts-test
## ---- 参考数据（票 19 / 31）----
seed: ## 写入 products / plans 参考数据到 PostgreSQL（幂等）：make seed [WHAT=products|plans]
	cd orchestrator && uv run --env-file ../.env haike-seed $(or $(WHAT),all)
plans-schema: ## 输出排障计划 JSON Schema（--enum 收窄 plan_id）
	cd orchestrator && uv run haike-plans-schema --enum

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
