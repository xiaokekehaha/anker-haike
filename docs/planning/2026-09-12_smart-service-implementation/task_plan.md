# 智能服务赛道实现（按 issues 逐票推进）

## 目标
按 ../2026-09-12_smart-service-tech-design/issues/ 的 50 张票顺序实现，一票一步，每票完成后更新票内勾选项与本目录 progress.md。

## 阶段
1. 票 01 Compose 骨架与 /health 聚合 — complete（Docker 实测通过：五容器 healthy，停机 3–4 s 可见，down/up 数据保留）
2. 票 02 前端空壳与健康灯 — complete（Codex 完成；14 项前端测试、构建与本机同源访问通过；镜像内前端构建与容器同源访问随票 01 Docker 实测通过。独立记录见 ../2026-09-12_smart-service-frontend-shell/）
3. 票 03 contracts 包 — in_progress（haike_contracts 5 模块已写出可导入；tests / schema / fixtures 为空，Makefile 无 schema 目标，待补齐验收）
4. 票 04 TS 类型生成与 CI 比对 — in_progress（Codex 认领；负责前端生成/校验、独立 CI、fixtures 骨架；不修改票 03 的 Python 契约，Claude Code 请跳过票 04）
5. 票 05 会话创建与 SSE 基础流 — pending
6. 票 06 前端 reducer 与 SSE 解析 — pending
7. 票 07 快照接口与投影表 — pending
8. 票 08 事件续接与恢复态 — pending（M1 会话骨架完成）
9. 票 09–14 模型层（M2） — pending
10. 票 15–25（M3）、26–36（M4）、37–41（M5）、42–45（M6）、46–50（M7） — pending

## 约定
- 代码目录：orchestrator/（FastAPI + LangGraph，uv 管理，Python 3.12）、frontend/（Vite + React 19 + TS）、contracts/（Pydantic 模型与 Schema）、config/（models.yaml 等）、deploy/（Compose 辅助文件）、根目录 docker-compose.yml 与 Makefile。
- 本机 Docker：colima + docker CLI + compose 插件（2026-09-12 起可用），Compose 验收项可在本机实测。
- 每票完成：勾选票内验收项、票 Status 改为 done、progress.md 追加记录、不合期望处写 findings.md。

## Next Step
票 01、02 完成。下一票：收尾票 03（补单测、`make schema` 导出三份 JSON Schema、票面勾选）。建议先提交当前工作区。
