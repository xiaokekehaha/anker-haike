# L3 闭环与五难点深化：设计与规划

## 目标
在现有 L2 引导系统（LangGraph 状态图 + WeKnora 检索 + 规则检查点 + 会话记忆 V2）之上，补齐赛题要求的 L3 业务办理闭环，并按五个难点（看图 / 问清 / 分流 / 接稳 / 幻觉）做深化设计，产出可直接拆票开发的设计系列与分阶段交付计划。输入见 [findings.md](findings.md) 与 [差距分析](../2026-09-14_hackathon-brief-gap-analysis/gap-analysis.md)。

## 阶段
- [x] 阶段 0：锚点核查（契约、状态图节点与路由、动作应用、reducer 输出、规则 API、管理台端点、迁移、前端卡片分发、models.yaml、ingest 元数据）
- [x] 阶段 1：前置决策 [00_decisions.md](00_decisions.md)
- [x] 阶段 2：范围、演示用例与验收 [01_scope-acceptance.md](01_scope-acceptance.md)
- [x] 阶段 3：目标架构与状态图改造 [02_target-architecture.md](02_target-architecture.md)
- [x] 阶段 4：四个新增能力层设计 —— [03_action-layer.md](03_action-layer.md)、[04_policy-engine.md](04_policy-engine.md)、[05_case-hitl.md](05_case-hitl.md)
- [x] 阶段 5：五难点深化 [06_five-difficulties.md](06_five-difficulties.md)
- [x] 阶段 6：数据、KPI 与评测 [07_data-evaluation.md](07_data-evaluation.md)
- [x] 阶段 7：交付计划与 P0 拆票 [08_delivery-plan.md](08_delivery-plan.md)、[issues/](issues/README.md)
- [x] 阶段 7b：产品跟进清单与数据加速剧本 [09_product-followup-checklist.md](09_product-followup-checklist.md)
- [x] 阶段 8：用户于 2026-09-14 授权开始开发；采用三项 P0 动作、domestic 默认通道，AWS 可选。

## 开发阶段

### P0-A：契约、模拟后端、动作层、政策引擎（51–54）
**Status:** complete

### P0-B：服务上下文、方案、执行、咨询、案件、审批（55–60）
**Status:** 功能开发收口（见 19）

### P0-C：情绪、视觉、多意图、KPI（61–64）
**Status:** 功能开发收口；真实数据评测不在本次结束条件内（见 19）

### P0-D：回归、演示巡检与发布文档（66）
**Status:** 必要功能验证已完成；剩余回放、评测与发布按用户要求停止扩展

## 决策
- 沿用 2026-09-12 设计系列的体例（编号文档 + issues 票）与全部既有边界（KnowledgeAdapter / ModelRouter / 规则检查点 / 执行契约），只做增量。
- 业务系统全部为模拟后端，接口形状按真实系统设计；政策规则为演示规则，来源标注为「待真实 SOP 替换」。
- 政策判定、授权门、动作执行零 LLM；LLM 只做理解、抽取、措辞。
- 票号从 51 起续接上一系列，避免与 01–50 混淆。

## 文件清单
task_plan.md · findings.md · 00_decisions.md · 01_scope-acceptance.md · 02_target-architecture.md · 03_action-layer.md · 04_policy-engine.md · 05_case-hitl.md · 06_five-difficulties.md · 07_data-evaluation.md · 08_delivery-plan.md · issues/README.md · issues/51–66 · progress.md

## 关联目录
- P1：[2026-09-14_l3-p1-real-data-multicategory](../2026-09-14_l3-p1-real-data-multicategory/task_plan.md)（票 67–80）
- P2：[2026-09-14_l3-p2-platform-scale](../2026-09-14_l3-p2-platform-scale/task_plan.md)（票 81–89）

## 当前交付状态

按用户最新要求“Step back 功能开发完成就结束”，本次功能开发收口，见 [19_functional-delivery.md](19_functional-delivery.md)。上下文与业务对象治理、执行恢复、任务归属、方案审批、情绪分流、进度展示、案件结案/重开和故障追问链路已落地。解释器 .10，症状分类与计划配置 .2。

不再自动扩充回放、照片评测、录屏或发布。旧版本证据不能作为当前版本发布验收；业务后端和政策仍为演示配置。本次结束不代表生产发布验收完成。
