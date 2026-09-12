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
