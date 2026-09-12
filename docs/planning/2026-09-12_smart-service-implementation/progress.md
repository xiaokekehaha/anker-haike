# 工作记录

## 2026-09-12
- 读取 issues/ 50 张票与 00–09 设计文档，确认从票 01 起步。
- 环境探查：macOS，系统 Python 3.9.6，uv 0.12.9 可用并安装了 CPython 3.12.14；node 26.8.1 + npm；无 docker / docker compose，无 Docker Desktop / OrbStack / colima。
- 核对 WeKnora：最新发布 v0.8.0（2026-09-03）；官方 compose 依赖 app + docreader + postgres(paradedb pg17) + redis，可选 frontend；app 健康接口 `GET /health`；HTTP API 前缀 `/api/v1`，鉴权头 `X-API-Key`。
- 票 01：写出 docker-compose.yml（orchestrator / postgres / redis / weknora-app / weknora-docreader，UI 为 profile）、Makefile、README、orchestrator 包（settings、health 探测与聚合、live 探针、Dockerfile、uv.lock）、config/models.yaml 初版、PostgreSQL 初始化脚本。6 个单元测试通过；本机 uvicorn 起服务后 /health 对未启动的 db / redis / weknora 各自报 down 并返回 503，models 通道按 .env 报 deepseek 就绪。
- 发现另一会话在同一工作树并行开发票 01（app/core、app/api、asyncpg、requirements.lock），用户确认以本会话为准；对方文件已移至 /tmp/haike-superseded-impl，吸收其 3 s 缓存与 `?force=` 设计。分支已在 feat/smart-service-impl。
- 用户要求安装 Docker：通过 Homebrew 安装 colima + docker CLI + compose 插件（后台进行）。
- 上一会话中断处：票 03 contracts 包已写出 5 个模块（未登记）；本会话先回头完成票 01 的 Docker 实测。
- 票 01 Docker 实测：colima 已运行；`make up` 首次拉取镜像 + 构建 orchestrator 镜像（含前端构建阶段）成功，五容器 healthy。/health 逐组件 ok；停 redis / weknora-app / postgres 后 3 s / 4 s / 3 s 内可见 down，恢复 3–4 s；postgres 停机时 503。`make down` → `make up` 后 haike 库数据保留。首页静态 200，日志无 error。票 01 标 done，票 02 的容器级验收随之补齐。
- 发现两个 Claude Code 会话同时在收尾票 03（contracts/tests 被互相覆盖）。约定：原会话为 A（会话骨架线，票 03/05/07/08），本会话为 B（模型层线，票 09–12），Codex 前端线（04/06）。B 已撤回对 05/07 的认领，不再改 `contracts/`；票 03 由 A 按其测试收尾。
- 票 03 收尾（A）：以磁盘现状重跑——contracts/tests 62 项通过（15 事件 + 6 动作一正一负、快照、导出）；`make contracts` 三份 Schema 重复导出零差异；`make contracts-check` 故意改模型后退出 1、还原后通过；ruff 与后端 6 项测试通过。删掉 A 重复加的 Makefile 契约段，保留 B 的并补 .PHONY。票 03 标 done，已提交 d325e45（该提交同时带入了 Codex 票 04 的前端类型生成文件）。
