# 2026-09-12_smart-service-tech-design 整体功能验证与完成情况盘点

## Goal
在其他在途任务（模型连通性、票 42 两家评测、步骤反馈报错诊断）落地后，对 50 张票做一次整体功能验证，列出已完成、未完成与遗留问题。

## Phases
1. 摸底与基线 — complete
   - 读取票据索引、已有验收报告（2026-09-13_completion-verification）、三个在途任务的计划与结论。
2. 自动化回归 — complete
   - 后端 / 前端 / 契约 / 生成器 / lint / 构建 / 数据库版本 / stub 巡检 / 三条录制包重放。
3. 真实服务验收 — complete
   - 六组真实 HTTP 场景、模型直连探测、浏览器 A1 全流程与新模型弹窗。
4. 盘点与报告 — complete
   - 产出 report.md：完成 / 未完成 / 遗留问题三类。

## Next Step
已完成。报告见 report.md；缺口是否处理由用户决定。

## Errors Encountered
- 首轮真实场景 a3 起 `RemoteProtocolError`：并非缺陷，是其他任务在 09:19 重建了 orchestrator 容器，连接被切断；容器稳定后重跑通过。
- a3 需要 `app.replay.scenarios`，直接用系统 python 运行报 ModuleNotFoundError；改为在 orchestrator 目录下 `uv run python` 执行后通过。
- 首次 `make replay-verify` 报 models_ver 不兼容（录制 .1 / 当前 .2）；录制包于 09:12 被重录为 .2 后三条全部通过。
