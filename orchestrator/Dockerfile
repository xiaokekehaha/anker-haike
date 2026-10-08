FROM node:24-alpine AS frontend-build
ARG NPM_REGISTRY=https://registry.npmjs.org/
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=$NPM_REGISTRY
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
# 第二入口：管理员观测台 /admin/（多页构建，产物在 dist/admin/index.html）
COPY frontend/admin ./admin
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_SYSTEM_PYTHON=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv

# 依赖层单独缓存；uv.lock 保证版本锁定。haike-contracts 是 ../contracts 的本地 editable 包（票 05）
COPY contracts /contracts
COPY orchestrator/pyproject.toml orchestrator/uv.lock ./
# 构建机网络受限时用镜像源：docker compose build --build-arg UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_INDEX_URL=https://pypi.org/simple
ENV UV_INDEX_URL=$UV_INDEX_URL
RUN uv sync --frozen --no-dev --no-install-project
ENV TIKTOKEN_CACHE_DIR=/srv/.cache/tiktoken
RUN .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

COPY orchestrator/app ./app
# 票 47：启动期迁移校验需要 alembic.ini 与 migrations/
COPY orchestrator/alembic.ini ./alembic.ini
COPY orchestrator/migrations ./migrations
COPY config ./config
# 主办方订单 / 经销商 / Q&A（data/official，由 app.official.build 从 xlsx 导出）
COPY data/official ./data/official
# 票 43：回放录制包随镜像打包（REPLAY_CASE_ID=<case_id> 启用；清单不符启动即失败）
COPY replay ./replay
# 票 02：镜像内构建前端，不依赖宿主机事先生成 dist
COPY --from=frontend-build /frontend/dist ./static/

# 容器内 app 装在 /srv/app，settings.REPO_ROOT 解析为 /。CONFIG_DIR 是 config/ 下所有加载的统一基准，
# 新增配置文件只要放进 config/ 就能被找到，不必再逐个补 *_CONFIG_PATH（下面这些保留为显式覆盖）。
ENV PATH="/srv/.venv/bin:$PATH" STATIC_DIR=/srv/static \
    CONFIG_DIR=/srv/config OFFICIAL_DATA_DIR=/srv/data/official \
    MODELS_CONFIG_PATH=/srv/config/models.yaml \
    CATALOG_CONFIG_PATH=/srv/config/products.yaml \
    PLANS_CONFIG_PATH=/srv/config/plans.yaml \
    FAULT_CARDS_CONFIG_PATH=/srv/config/fault_cards.yaml \
    RULES_CONFIG_PATH=/srv/config/rules/safety_terms.yaml \
    RETRIEVAL_CONFIG_PATH=/srv/config/retrieval.yaml \
    CONVERSATION_CONFIG_PATH=/srv/config/conversation.yaml \
    REPLAY_DIR=/srv/replay KB_MANIFEST_PATH=/srv/replay/kb_manifest.json
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
