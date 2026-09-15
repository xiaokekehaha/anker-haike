# 本机项目服务暂停与恢复

日期：2026-09-13。用户约定：不开发时停止本项目服务，需要开发时再启动；只操作本项目的 PostgreSQL、Redis 等服务，其他项目不要动。

## 当前环境与数据

- 仓库：`/Users/xiaoke.zhou/Documents/workspace/anker-haike`。
- Docker context：`colima`，Colima profile：`default`。
- Compose 项目名：`haike`。业务栈定义在根目录 `docker-compose.yml`，Langfuse 栈定义在 `deploy/observability/compose.yaml`。
- PostgreSQL 数据存储在 `haike_postgres-data`，Redis 开启 AOF，存储在 `haike_redis-data`。知识库文件、数据库备份及观测栈也有独立命名卷。
- 日常暂停使用 `stop`，保留容器和数据卷；不要使用 `make reset`、`down -v`、卷清理或 `colima delete`。
- 正常停止不会清空数据库，但处理中请求会中断。Redis TTL 继续按实际时间计算。应用原有保留策略仍有效：本次容器配置会话保留 168 小时，恢复服务时后台清理会处理到期数据；保留卷不代表历史会话永久保留。

## 下次启动（在仓库根目录执行）

```bash
cd /Users/xiaoke.zhou/Documents/workspace/anker-haike
colima start
docker --context colima compose --profile ui up -d --wait --wait-timeout 180
make health
```

PostgreSQL、Redis、WeKnora、备份服务、后端和内置前端会一起启动，无需另外安装或手动启动数据库。主页面为 `http://localhost:8000`，WeKnora 管理页为 `http://localhost:8081`。只启动 Colima 不足以恢复此前手动停止的容器，需要执行 Compose 命令。保留现有 `.env`，不用重新初始化数据库或导入知识库。

上述命令复用现有镜像。需要让后端或内置前端的源码改动进入镜像时，执行 `make up`（会构建），随后 `make health`。若健康等待超时，检查 `docker --context colima compose ps` 和相应服务日志。

需要前端热更新时，另开终端执行：

```bash
npm --prefix frontend run dev -- --port 5173 --strictPort
```

访问 `http://localhost:5173`，API 代理到容器后端的 8000 端口。终端 `Ctrl+C` 停止。容器后端占用 8000 时不要同时在该端口运行 `make dev-api`。

需要 Langfuse 时，额外执行：

```bash
docker --context colima compose --env-file .env --env-file deploy/observability/.env -f docker-compose.yml -f deploy/observability/compose.yaml --profile observability up -d --wait --wait-timeout 180 langfuse-web langfuse-worker
```

观测页为 `http://localhost:3000`。复用已有观测栈配置及数据，更多说明见 [可观测栈手册](../../deploy/observability/README.md)。

## 下次停止

先在本项目的本机开发终端按 `Ctrl+C`，再执行：

```bash
docker --context colima compose --env-file .env --env-file deploy/observability/.env -f docker-compose.yml -f deploy/observability/compose.yaml --profile ui --profile observability stop --timeout 60
docker --context colima ps --format 'table {{.Names}}\t{{.Status}}'
```

该 Compose 命令仅停止 `haike` 项目的业务栈和观测栈，包含它们各自的 PostgreSQL 与 Redis。不要使用全局批量停止命令。

只有确认当前 Colima 实例没有其他项目需要继续运行的容器或工作负载时，才能执行 `colima stop`；若有其他项目在使用该实例，保留 Docker 运行，仅停止本项目容器。不得停止其他项目的本机数据库或其他 Docker context。

## 本次停机范围

- 本项目 13 个运行中容器（包括业务与观测栈）。
- 本项目本机 Vite：5173、5174、5175；临时后端：8780；embedding 测试桩：8099。
- 临时后端和 embedding 测试桩不属于日常启动步骤，仅在对应测试需要时恢复。
- 停止前当前 Docker context 中所有运行容器都属于 `haike`；其他项目及远程数据库未操作。
- 已核验：13 个容器全部退出，业务与观测 PostgreSQL / Redis 均以退出码 0 停止，9 个项目命名卷仍在。Langfuse web / worker 与备份循环等待 60 秒后由 Docker 结束（退出码 137）；未删除其数据卷。
- 确认当前实例没有运行容器后，已停止 Colima `default`。本次仅核验停机结果，未重新启动服务；下次启动后执行健康检查。

## 2026-09-14 恢复记录

- 应用户要求启动 Colima `default`，通过带 `ui` / `observability` profile 的 Compose `start --wait --wait-timeout 180` 恢复本项目已有 13 个容器，复用停机前镜像和数据。
- 已启动 Vite 开发页面 `http://127.0.0.1:5173/`。临时 8780 后端、8099 embedding 测试桩及重复 Vite 实例不属于日常服务，未启动。
- Compose 健康等待通过；后端 `/health` 返回 `status=ok`，数据库、Redis、WeKnora 及默认模型通道配置正常。
- 本次只恢复已有服务，没有重建镜像；工作区尚在开发的后端改动需要之后构建镜像才会进入容器。
