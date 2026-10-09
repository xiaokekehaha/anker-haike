# RELEASE 20261009-5307876

生成时间：2026-10-09T06:00:52Z　Git：5307876（feat/service-plan-base）

## 冻结版本（04 §4）

| 项 | 值 |
| --- | --- |
| 镜像 tag | `ghcr.io/xiaokekehaha/haike-orchestrator:20261009-5307876`（CI 构建；本机 `make up` 为 haike/orchestrator:dev） |
| prompt_ver | system 2026-09-25.1 / reply 2026-10-08.1 |
| models.yaml | 2026-09-18.2（TBD / TODO 计数：0，须为 0 才能冻结，票 42） |
| bake-off | models.yaml 2026-09-13.5，bakeoff.yaml 2026-09-12.1，repeats=3（reports/bakeoff/bakeoff.md；裁决理由见 docs/planning/2026-09-12_smart-service-bakeoff/findings.md） |
| rules_ver | 2026-10-08.1 |
| actions_version | 2026-10-08.1 |
| emotion_policy / vision_vocab | 2026-09-18.1 / 2026-10-08.1 |
| official data | 0cc02e6531d6 |
| products / 官方 Q&A | 2026-10-08.1 / 0cc02e6531d6 |
| kb_ver | 0cc02e6531d6+text-embedding-v4 |
| WeKnora 镜像 tag | v0.8.0 |
| 回放包清单 | t13_code_miss,t14_hardware_fault,t29_out_of_warranty,t2_delivered,t45_safety_dealer,t55_main,t8_reship |
| 业务表迁移 head | 0009 |
| config 快照 | `releases/20261009-5307876/config/`（回滚用：`make rollback REL=<上一版>`） |

## 灰度验证顺序（04 §4）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42，model-selection §3.8）
2. 结构化 fixture 跑协议与规则测试（contracts / 后端 CI 绿）
3. 重新录制回放包并更新清单（票 43）
4. 演示机 `make up` 后 `make health` 全 ok，`make db-backup` 一次

## 回滚

`make rollback REL=<上一版 release_id>`：切回该版 config/ 并重启编排服务，5 分钟内健康检查通过即完成；不涉及数据迁移（迁移只前向，见 docs/runbook/database.md §4）。知识库回滚 `make kb-snapshot DIR=…`。
