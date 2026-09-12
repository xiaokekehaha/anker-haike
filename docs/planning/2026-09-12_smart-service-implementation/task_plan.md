# 智能服务赛道实现（按 issues 逐票推进）

## 目标
按 ../2026-09-12_smart-service-tech-design/issues/ 的 50 张票顺序实现，一票一步，每票完成后更新票内勾选项与本目录 progress.md。

## 阶段
1. 票 01 Compose 骨架与 /health 聚合 — complete（Docker 实测通过：五容器 healthy，停机 3–4 s 可见，down/up 数据保留）
2. 票 02 前端空壳与健康灯 — complete（Codex 完成；14 项前端测试、构建与本机同源访问通过；镜像内前端构建与容器同源访问随票 01 Docker 实测通过。独立记录见 ../2026-09-12_smart-service-frontend-shell/）
3. 票 03 contracts 包 — complete（A 收尾：62 项测试、`make contracts` 导出稳定、`make contracts-check` 漂移检测验证可用）
4. 票 04 TS 类型生成与 CI 比对 — complete（Codex；50 项前端测试 + 6 项生成器回归、双端 fixtures、类型检查与构建通过；CI 已接入，未触发远端运行）
5. 票 05 会话创建与 SSE 基础流 — complete（A：orchestrator/app/sessions，11 项测试 + 真实 Postgres 链路实测）
6. 票 06 前端 reducer 与 SSE 解析 — complete（Claude Code B，含前端集成）
7. 票 07 快照接口与投影表 — complete（A：GET /sessions/{id}、timeline 折叠、sessions-rebuild CLI，真实 Postgres 删行重建一致）
8. 票 08 事件续接与恢复态 — complete（Codex 2026-09-12 补齐前端恢复、去重与请求生命周期；后端此前已实测）
9. 票 09–14 模型层（M2） — complete（Claude Code B：09–12 complete；13 / 14 后端 complete，前端 AssistantBubble / 替换标注待 Codex）
10. 票 15–25（M3）、26–36（M4）、37–41（M5）、42–45（M6）、46–50（M7） — pending（其中 15、16、17、18、19、26、27、28、29、31、33 已由 Claude Code B 完成，32 核心完成；前端集成完成）

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
A：46 / 47 / 49 完成，38 后端全 done。42 bake-off 由 Claude Code C 完成（评测包 + DeepSeek 单家实测 + models.yaml 冻结 2026-09-13.1，记录见 ../2026-09-12_smart-service-bakeoff/；其他厂商 key 到位后 `make bakeoff` 补跑即可）；44 可观测由 Codex 实现中；剩余无 Owner：50 告警与运行手册（依赖 44）、48 数据保留（依赖 44）、43 回放已由 Claude Code B 完成（2026-09-13）、45 巡检（依赖 37/43，现无阻塞）。前端堆积：06 → 08/16/21/23/28/38 前端部分（Codex）。

## Codex 接续更新（2026-09-12）
票 08 / 38 前端已补齐；票 23 原始验收完成，追加的纠错 / verify 联动仍依赖后续实现。前端 96 项测试、6 项生成器测试、typecheck/build/contracts:check 通过。当前工作区仍有 Claude Code 持续开发，整体进度以各票最新 Status 和验收勾选为准；上方早期阶段概览不代表所有后续功能已完成。接续记录见 ../2026-09-12_codex-development-continuation/。
