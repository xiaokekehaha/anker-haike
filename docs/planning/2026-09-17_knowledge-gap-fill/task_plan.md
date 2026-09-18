# 知识库缺口补齐与固定流程复核（2026-09-17）

用户要求：从官方站采集资料补齐知识库；复核固定处理流程（`config/plans.yaml`），不合理处改掉。
确认范围：扫地机 4 个症状缺口 + 头戴耳机（headphones）成为可排障品类；走完整入库验收流程。

## 现状（开工前实测）

`symptom_taxonomy` 登记但 `plans` 无计划：

| 品类 | 症状码 | 后果 |
|---|---|---|
| robot_vacuum | `water_leak` `mop_failure` `navigation_failure` `app_connection` | 症状识别成功，进排障直接 R5 |
| headphones | 整个品类没有 taxonomy / plans / fault_cards | Space One 两篇官方资料已入库但排障用不上 |

`plans.yaml` 复核发现的流程缺陷见 `findings.md`。

## 步骤

1. [x] `data/knowledge/sources/anker_official.yaml` 追加 11 篇来源，批次 version 递增
2. [x] `make kb-official-fetch` → 逐篇对照缓存原文核对中文摘要 → 回填 `reviewed_source_sha256`
3. [x] `make kb-official-build` 生成 `data/knowledge/kb_manual/official_*.md`
4. [x] `config/plans.yaml`：证据段登记新锚点；新增计划；修正已有流程缺陷
5. [x] `config/symptom_taxonomy.yaml`：新增 headphones 词表与判别题
6. [x] `config/fault_cards.yaml`：新增 headphones 品类卡与两张 SKU 卡；X10 卡补新故障
7. [x] 更新 `orchestrator/tests/test_plans.py` 等受影响断言，补回归
8. [x] `make lint` + 相关 pytest
9. [x] `make kb-snapshot-export` → `make kb-ingest` → `make kb-official-verify` → `make kb-anchors`
10. [x] 写 `report.md`

## 约束

- 采集只走 `app/knowledge/official.py` 既有管线：官方 HTTPS 支持站、`/article-description/` 路径、正文哈希固定后才 build。
- 官方文档 `scope: sku`，因此引用官方证据的计划一律 `applies_to.scope: sku`，不冒充品类通用。
- 语义单元整块（标题 + 摘要）不超过子块预算 200 字符。
- 演示样本 `manual_* / faq_*` 的既有计划不动证据，只修流程。
