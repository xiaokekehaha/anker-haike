# 票据索引与依赖图（L3 系列，接续 01–50）

由 2026-09-14 设计系列 00–08 拆出。一票一文件，`Blocked by` 为阻塞边；无阻塞的票可立即开始（51、52、54、65）。状态：todo / in-progress / done / done-with-gap。

| # | 票 | Blocked by | 估算（人日） | 阶段 |
| --- | --- | --- | --- | --- |
| 51 | [契约扩展一次落地](51-contracts-l3-extension.md) | — | 2 | P0-A |
| 52 | [模拟后端：协议、演示表、seed、故障注入](52-mock-backends.md) | — | 2 | P0-A |
| 53 | [动作注册表、授权门与执行器](53-action-registry-gate-executor.md) | 52 | 3 | P0-A |
| 54 | [售后政策规则引擎](54-policy-engine.md) | — | 3 | P0-A |
| 55 | [服务上下文节点与 ContextCard](55-service-context.md) | 51, 54 | 2 | P0-B |
| 56 | [propose 节点、方案模板与 ProposalCard](56-propose-proposal-card.md) | 51, 54, 55 | 2.5 | P0-B |
| 57 | [authorize / execute / track 与 ExecutionCard](57-authorize-execute-track.md) | 53, 56, 59 | 3 | P0-B |
| 58 | [简单咨询快路径](58-consult-fast-path.md) | 51, 53 | 2.5 | P0-B |
| 59 | [案件对象与状态机](59-case-lifecycle.md) | 51 | 2.5 | P0-B |
| 60 | [最小人工协同回路](60-hitl-approval-loop.md) | 57, 59 | 3.5 | P0-B |
| 61 | [情绪四级、轨迹与策略矩阵](61-emotion-four-levels-strategy.md) | 51 | 2.5 | P0-C |
| 62 | [看图结构化故障定位与 RetakeCard](62-vision-fault-localization.md) | 51 | 3 | P0-C |
| 63 | [多意图任务队列与自动接续](63-multi-intent-task-queue.md) | 51, 58 | 2 | P0-C |
| 64 | [KPI 采集、Dashboard 与评测集骨架](64-kpi-ratings-dashboard-evalsets.md) | 57, 58, 59 | 3 | P0-C |
| 65 | [Bedrock provider 与 aws 通道（可选）](65-bedrock-provider-aws-lane.md) | — | 1.5 | 可选 |
| 66 | [演示回放包、巡检、RELEASE 六元组](66-demo-replay-inspection-release.md) | 51–64 | 2 | P0-D |

```
51 ──┬─→ 55 ─→ 56 ─→ 57 ─→ 60
     ├─→ 58 ←─ 53 ←─ 52      ▲
     ├─→ 59 ────────────────┘
     ├─→ 61   62   63 ←─ 58
     └─→ 64 ←─ 57, 58, 59
54 ──→ 55, 56            65（独立）      66 ←─ 全部
```

演示用例与票的对应：A4 → 58；A5 → 55/56/57/59；A6 → 54/57/60；A7 → 63；A8 → 61；A9 → 62；KPI → 64。
