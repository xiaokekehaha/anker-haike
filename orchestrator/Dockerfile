FROM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
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
RUN uv sync --frozen --no-dev --no-install-project

COPY orchestrator/app ./app
COPY config ./config
# 票 02：镜像内构建前端，不依赖宿主机事先生成 dist
COPY --from=frontend-build /frontend/dist ./static/

ENV PATH="/srv/.venv/bin:$PATH" MODELS_CONFIG_PATH=/srv/config/models.yaml STATIC_DIR=/srv/static
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
