# 票据索引与依赖图（L3 P2，接续 67–80）

前置：P0 [l3-closed-loop-design/issues](../../2026-09-14_l3-closed-loop-design/issues/README.md)、P1 [l3-p1-real-data-multicategory/issues](../../2026-09-14_l3-p1-real-data-multicategory/issues/README.md)。

| # | 票 | Blocked by | 估算（人日） | 类别 |
| --- | --- | --- | --- | --- |
| 81 | [Bedrock 通道 bake-off 与切换演练](81-bedrock-bakeoff-switch.md) | P0 65, 66；D-L3-2；AWS 权限 | 2 | 演示加分 |
| 82 | [多语言 zh / en](82-multilingual-zh-en.md) | P0 66；P1 70 | 4 | 演示加分 |
| 83 | [多模型交叉审核评估](83-cross-model-review-eval.md) | P0 66；P1 72 | 2.5 | 正确性 |
| 84 | [案件级定时与长流程](84-case-scheduler-step-functions.md) | P1 79；85 | 3 | 运行形态 |
| 85 | [多副本运行协调](85-multi-replica-coordination.md) | P0 66；多副本部署时前置 | 4 | 运行形态 |
| 86 | [知识审核发布治理 UI](86-knowledge-publish-governance-ui.md) | P1 70, 80 | 3 | 正确性 |
| 87 | [外网官方资料补充检索](87-external-official-search.md) | P0 66；P1 78 | 3 | 能力探索 |
| 88 | [生产就绪收口](88-production-readiness-closeout.md) | P0 66 | 3 | 运行形态 |
| 89 | [跨会话用户级记忆评估](89-cross-session-memory-eval.md) | P1 80；身份方案 | 1.5 | 能力探索 |
| 合计 | | | ≈ 26 | |

```
P0 65 ─→ 81          P1 70 ─→ 82, 86 ←─ P1 80 ─→ 89
P1 72 ─→ 83          P1 79 ─→ 84 ←─ 85          P1 78 ─→ 87
P0 66 ─→ 88（可最早开工）
```
可最早开工：88（只依赖 P0 收口）、85（部署形态决定）。
