# 智能服务赛道（anker-haike）

扫地机器人售后智能服务：情绪安抚、产品消歧、多模态故障定位、分步排障、升级与凭证核对。设计文档见 [docs/planning/2026-09-12_smart-service-tech-design/](docs/planning/2026-09-12_smart-service-tech-design/)，实现进度见 [docs/planning/2026-09-12_smart-service-implementation/](docs/planning/2026-09-12_smart-service-implementation/)。

## 组成

| 目录 | 内容 |
| --- | --- |
| orchestrator/ | FastAPI + LangGraph 编排服务（Python 3.12，uv 管理） |
| frontend/ | Vite + React 19 + TypeScript 单页，构建产物由编排服务同源托管 |
| contracts/ | 事件 / 动作 / 快照的 Pydantic 模型与 JSON Schema |
| config/ | models.yaml 模型路由等配置 |
| deploy/ | Compose 辅助文件（PostgreSQL 初始化脚本等） |

## 启动（Docker）

前置：Docker 24+ 与 Compose v2。

```bash
cp .env.example .env        # 填 DEEPSEEK_API_KEY 等
make up                     # 构建并拉起 orchestrator / postgres / redis / weknora-app / weknora-docreader
make health                 # 查看聚合健康
```

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000 | 编排服务与前端 |
| http://localhost:8000/health | 聚合健康：db / redis / weknora / models（按通道） |
| http://localhost:8080 | WeKnora API |
| http://localhost:8081 | WeKnora 网页（`make up` 一并启动；登录后经 nginx 代理 `/api/` 到 8080，用于查看知识库、建 tenant、取 API key） |

停止：`make down`（保留数据）。重置全部数据：`make reset`。首次拉起 WeKnora 镜像与 docreader 约需数分钟。

本机闲置时暂停项目、关闭 Colima，以及下次恢复 PostgreSQL / Redis / 前后端的完整步骤，见 [本机服务暂停与恢复](docs/claude/spec_local_services_lifecycle.md)。只停止本项目；其他项目使用同一 Docker 实例时保留该实例运行。

## 本机开发（不用 Docker）

```bash
make dev-sync               # uv 安装后端依赖
make dev-api                # 起编排服务，读根目录 .env
make test                   # 后端单元测试
```

没有 PostgreSQL / WeKnora 时，/health 会把对应组件报为 down，接口本身仍可用。

## 版本锁定

| 组件 | 版本 |
| --- | --- |
| WeKnora（app / docreader / ui） | v0.8.0 |
| PostgreSQL 镜像 | paradedb/paradedb:v0.22.2-pg17（含 pgvector） |
| Redis | 7.0-alpine |
| Python | 3.12，依赖锁定在 orchestrator/uv.lock |

## 数据库运维

迁移（Alembic）、每日备份、一键恢复与单点风险说明见 [docs/runbook/database.md](docs/runbook/database.md)。常用：`make db-upgrade`、`make db-backup`、`make db-backup-status`、`make db-restore FILE=…`。
