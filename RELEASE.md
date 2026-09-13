# RELEASE 20260913-4abcd4e-sync-085548

生成时间：2026-09-13T00:56:28Z　Git：4abcd4e（feat/smart-service-impl）

## 本地部署版本（正式冻结待验收缺口关闭）

| 项 | 值 |
| --- | --- |
| 镜像 tag | `haike/orchestrator:20260913-4abcd4e-sync-085548`（本机已构建并部署；未推送 GHCR） |
| prompt_ver | system 2026-09-12.1 / reply 2026-09-12.1 |
| models.yaml | 2026-09-13.1（TBD / TODO 计数：0，须为 0 才能冻结，票 42） |
| bake-off | models.yaml 2026-09-13.1，bakeoff.yaml 2026-09-12.1，repeats=3（reports/bakeoff/bakeoff.md；裁决理由见 docs/planning/2026-09-12_smart-service-bakeoff/findings.md） |
| rules_ver | 2026-09-12.1 |
| products / plans | 2026-09-12.1 / 2026-09-12.1 |
| kb_ver | 2026-09-12.1+stub-embedding-1024 |
| WeKnora 镜像 tag | v0.8.0 |
| 回放包清单 | a1_hair_wrap,a2_disambiguate,a3_receipt_channel |
| 业务表迁移 head | 0003 |
| config 快照 | `releases/20260913-4abcd4e-sync-085548/config/`（回滚用：`make rollback REL=<上一版>`） |

## 灰度验证顺序（04 §4）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42，model-selection §3.8）
2. 结构化 fixture 跑协议与规则测试（contracts / 后端 CI 绿）
3. 重新录制回放包并更新清单（票 43）
4. 演示机 `make up` 后 `make health` 全 ok，`make db-backup` 一次

## 回滚

`make rollback REL=<上一版 release_id>`：切回该版 config/ 并重启编排服务，5 分钟内健康检查通过即完成；不涉及数据迁移（迁移只前向，见 docs/runbook/database.md §4）。知识库回滚 `make kb-snapshot DIR=…`。

## 本次同步验收

- 镜像 ID：`sha256:3ea2c82bf8b3d3b6fa583329fd132d1e018b8ec50e463bed70c6c82f55af0500`。
- 源码为当前工作区：包含未提交的部署修复和用户已有模型配置修改，不能只按 HEAD 复现；文件哈希与改动清单见 `docs/planning/2026-09-13_completion-verification/deployment.json`。
- 6 组真实 HTTP 场景通过；浏览器 A1 与刷新恢复通过；后端 434 项回归通过。
- 真实照片 / 真实订单截图质量、双厂商逐 task 评测及票 32 的实现差异尚未关闭。本清单是本地部署记录，不宣称生产验收或正式冻结。
