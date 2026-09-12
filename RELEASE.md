# RELEASE drill-b

生成时间：2026-09-12T14:44:28Z　Git：d13c7fa（feat/smart-service-impl）

## 冻结版本（04 §4）

| 项 | 值 |
| --- | --- |
| 镜像 tag | `ghcr.io/xiaoke12345678/haike-orchestrator:drill-b`（CI 构建；本机 `make up` 为 haike/orchestrator:dev） |
| prompt_ver | system 2026-09-12.1 / reply 2026-09-12.1 |
| models.yaml | 2026-09-12.2-bad（TBD / TODO 计数：9，须为 0 才能冻结，票 42） |
| rules_ver | 2026-09-12.1 |
| products / plans | 2026-09-12.1 / 2026-09-12.1 |
| kb_ver | 2026-09-12.1+stub-embedding-1024 |
| WeKnora 镜像 tag | v0.8.0 |
| 回放包清单 | -（票 43 未录制） |
| 业务表迁移 head | 0002 |
| config 快照 | `releases/drill-b/config/`（回滚用：`make rollback REL=<上一版>`） |

## 灰度验证顺序（04 §4）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42，model-selection §3.8）
2. 结构化 fixture 跑协议与规则测试（contracts / 后端 CI 绿）
3. 重新录制回放包并更新清单（票 43）
4. 演示机 `make up` 后 `make health` 全 ok，`make db-backup` 一次

## 回滚

`make rollback REL=<上一版 release_id>`：切回该版 config/ 并重启编排服务，5 分钟内健康检查通过即完成；不涉及数据迁移（迁移只前向，见 docs/runbook/database.md §4）。知识库回滚 `make kb-snapshot DIR=…`。
