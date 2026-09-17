# RELEASE 20260917-845a268

生成时间：2026-09-17T02:02:42Z　Git：845a268（feat/grounded-citation）

## 冻结版本（04 §4）

| 项 | 值 |
| --- | --- |
| 镜像 tag | `ghcr.io/xiaoke12345678/haike-orchestrator:20260917-845a268`（CI 构建；本机 `make up` 为 haike/orchestrator:dev） |
| prompt_ver | system 2026-09-14.1 / reply 2026-09-12.1 |
| models.yaml | 2026-09-15.2（TBD / TODO 计数：0，须为 0 才能冻结，票 42） |
| bake-off | models.yaml 2026-09-13.5，bakeoff.yaml 2026-09-12.1，repeats=3（reports/bakeoff/bakeoff.md；裁决理由见 docs/planning/2026-09-12_smart-service-bakeoff/findings.md） |
| rules_ver | 2026-09-12.1 |
| policy_version | 2026-09-14.1 |
| actions_version | 2026-09-14.2 |
| emotion_policy / symptom_taxonomy / vision_vocab | 2026-09-14.1 / 2026-09-16.1 / 2026-09-15.6 |
| backends_mock seed | 2026-09-14.1 |
| products / plans | 2026-09-12.1 / 2026-09-16.1 |
| kb_ver | 2026-09-12.1+text-embedding-v4 |
| WeKnora 镜像 tag | v0.8.0 |
| 回放包清单 | a1_hair_wrap,a2_disambiguate,a3_receipt_channel,a4_logistics,a5_replacement,a6_human_approval,a7_multi_intent,a8_emotion |
| 业务表迁移 head | 0007 |
| config 快照 | `releases/20260917-845a268/config/`（回滚用：`make rollback REL=<上一版>`） |

## 灰度验证顺序（04 §4）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42，model-selection §3.8）
2. 结构化 fixture 跑协议与规则测试（contracts / 后端 CI 绿）
3. 重新录制回放包并更新清单（票 43）
4. 演示机 `make up` 后 `make health` 全 ok，`make db-backup` 一次

## 回滚

`make rollback REL=<上一版 release_id>`：切回该版 config/ 并重启编排服务，5 分钟内健康检查通过即完成；不涉及数据迁移（迁移只前向，见 docs/runbook/database.md §4）。知识库回滚 `make kb-snapshot DIR=…`。
