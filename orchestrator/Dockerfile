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

COPY orchestrator/app ./app
# 票 47：启动期迁移校验需要 alembic.ini 与 migrations/
COPY orchestrator/alembic.ini ./alembic.ini
COPY orchestrator/migrations ./migrations
COPY config ./config
# 票 43：回放录制包随镜像打包（REPLAY_CASE_ID=<case_id> 启用；清单不符启动即失败）
COPY replay ./replay
# 票 02：镜像内构建前端，不依赖宿主机事先生成 dist
COPY --from=frontend-build /frontend/dist ./static/

# 容器内 REPO_ROOT 解析为 /，settings 里所有 config 默认路径都要显式指到 /srv/config（票 19/31/15 的配置在容器里首次启用）
ENV PATH="/srv/.venv/bin:$PATH" STATIC_DIR=/srv/static \
    MODELS_CONFIG_PATH=/srv/config/models.yaml \
    CATALOG_CONFIG_PATH=/srv/config/products.yaml \
    PLANS_CONFIG_PATH=/srv/config/plans.yaml \
    RECEIPT_REFERENCE_CONFIG_PATH=/srv/config/receipt_reference.yaml \
    FAULT_CARDS_CONFIG_PATH=/srv/config/fault_cards.yaml \
    RULES_CONFIG_PATH=/srv/config/rules/safety_terms.yaml \
    RETRIEVAL_CONFIG_PATH=/srv/config/retrieval.yaml \
    REPLAY_DIR=/srv/replay KB_MANIFEST_PATH=/srv/replay/kb_manifest.json
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
