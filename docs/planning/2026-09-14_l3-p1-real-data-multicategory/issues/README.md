# 票据索引与依赖图（L3 P1，接续 51–66）

前置：P0 票见 [l3-closed-loop-design/issues](../../2026-09-14_l3-closed-loop-design/issues/README.md)。「真实数据」指组织方交付的脱敏工单 / 知识库 / 名录 / SOP。

| # | 票 | Blocked by | 估算（人日） | Epic |
| --- | --- | --- | --- | --- |
| 67 | [多品类产品目录生成](67-multicategory-catalog.md) | P0 66；真实知识库 | 2 | E1 |
| 68 | [症状体系多品类扩表](68-symptom-taxonomy-multicategory.md) | 71；P0 58 | 3 | E1 |
| 69 | [多品类故障卡与计划编写流程](69-faultcards-plans-authoring.md) | 67, 68, 70 | 3 | E1 |
| 70 | [知识按品类 / 区域入库与发布状态过滤](70-knowledge-region-publish-state.md) | P0 55；真实知识库 | 2.5 | E1 |
| 71 | [脱敏工单清洗与结构化管线](71-ticket-cleaning-pipeline.md) | 真实工单 | 4 | E2 |
| 72 | [评测集替换为真实样本与保留集基线](72-evalsets-real-samples.md) | 71；P0 64 | 2 | E2 |
| 73 | [授权经销商真实名录导入](73-dealer-directory-import.md) | 真实名录；P0 54 | 1.5 | E2 |
| 74 | [SOP → 政策规则编译与审核流](74-sop-to-policy-compile.md) | 真实 SOP；P0 54 | 3 | E3 |
| 75 | [政策条款入知识库 kb_policy](75-policy-clauses-into-kb.md) | 74, 70 | 1.5 | E3 |
| 76 | [refund.create 与补偿一致性账本](76-refund-action-commitments-ledger.md) | P0 57, 60；74 | 3 | E4 |
| 77 | [address.update 与 rma.dispatch](77-address-update-rma-dispatch.md) | P0 57, 58；74 | 2.5 | E4 |
| 78 | [检索评测集标注与六开关启用](78-retrieval-switches-enable.md) | 71；P0 64 | 3 | E5 |
| 79 | [案件跟踪状态回写与主动告知](79-case-tracking-notifications.md) | P0 57, 59, 60 | 2 | 补 |
| 80 | [服务质量闭环 P0a / P0b 对接](80-quality-loop-integration.md) | P0 59, 60, 64 | 4 | 补 |
| 合计 | | | ≈ 37 | |

```
真实工单 ─→ 71 ─→ 68 ─→ 69 ←─ 67 ←─ 真实知识库 ─→ 70
              └─→ 72, 78
真实名录 ─→ 73        真实 SOP ─→ 74 ─→ 75, 76, 77
P0 57/59/60 ─→ 79, 80
```
数据未到手时可先做：71 / 73 / 74 的管线与 mapping 骨架（合成样本验证）、79、80。
