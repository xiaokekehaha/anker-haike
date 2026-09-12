# 智能服务赛道实现（按 issues 逐票推进）

## 目标
按 ../2026-09-12_smart-service-tech-design/issues/ 的 50 张票顺序实现，一票一步，每票完成后更新票内勾选项与本目录 progress.md。

## 阶段
1. 票 01 Compose 骨架与 /health 聚合 — complete（Docker 实测通过：五容器 healthy，停机 3–4 s 可见，down/up 数据保留）
2. 票 02 前端空壳与健康灯 — complete（Codex 完成；14 项前端测试、构建与本机同源访问通过；镜像内前端构建与容器同源访问随票 01 Docker 实测通过。独立记录见 ../2026-09-12_smart-service-frontend-shell/）
3. 票 03 contracts 包 — in_progress（Claude Code A 收尾中：contracts/tests、`make contracts` 导出 schema/、`make contracts-check`）
4. 票 04 TS 类型生成与 CI 比对 — in_progress（Codex 认领；负责前端生成/校验、独立 CI、fixtures 骨架；不修改票 03 的 Python 契约，Claude Code 请跳过票 04）
5. 票 05 会话创建与 SSE 基础流 — pending（Claude Code A，票 03 后）
6. 票 06 前端 reducer 与 SSE 解析 — pending（前端票，建议 Codex 在票 04 后认领）
7. 票 07 快照接口与投影表 — pending（Claude Code A）
8. 票 08 事件续接与恢复态 — pending（M1 会话骨架完成）
9. 票 09–14 模型层（M2） — in_progress（Claude Code B：09 进行中，10–12 已排队；13–14 依赖票 05，届时再协调）
10. 票 15–25（M3）、26–36（M4）、37–41（M5）、42–45（M6）、46–50（M7） — pending

## 并行分工（2026-09-12 起，三方同一工作树）
- **Claude Code A（会话骨架线）**：票 03 收尾 → 05 → 07 → 08；目录 `contracts/`、`orchestrator/app/sessions/`（含事件日志、快照）。
- **Claude Code B（模型层线）**：票 09 → 10 → 11 → 12；目录 `orchestrator/app/models/`、`orchestrator/scripts/`、`config/models.yaml`。独立记录见 ../2026-09-12_smart-service-model-layer/。
- **Codex（前端线）**：票 04 → 06（建议）；目录 `frontend/`、`contracts/fixtures/`、`.github/workflows/`。
- 共享文件（Makefile、orchestrator/pyproject.toml、orchestrator/app/main.py）只追加不重排；改动前先 `git diff` 看对方有无未提交改动。

## 约定
- 代码目录：orchestrator/（FastAPI + LangGraph，uv 管理，Python 3.12）、frontend/（Vite + React 19 + TS）、contracts/（Pydantic 模型与 Schema）、config/（models.yaml 等）、deploy/（Compose 辅助文件）、根目录 docker-compose.yml 与 Makefile。
- 本机 Docker：colima + docker CLI + compose 插件（2026-09-12 起可用），Compose 验收项可在本机实测。
- 每票完成：勾选票内验收项、票 Status 改为 done、progress.md 追加记录、不合期望处写 findings.md。

## Next Step
A：收尾票 03 后进入票 05；B：票 09 模型配置与路由；Codex：票 04。
