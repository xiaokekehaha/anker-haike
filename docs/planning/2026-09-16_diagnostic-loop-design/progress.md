# Progress

## 2026-09-16

- 复核 verify、graph、计划配置与现有充电判别问题。
- 采用 codebase-design 与 planning-with-files；设计目标为减少分散终止决策、让步骤反馈进入事实更新。
- 已完成 design.md：复用现有 decision 与事实模型，增加步骤观察反馈、耗尽后评估、统一终止语义和分阶段迁移。
- 明确知识不足时仍可合理结束，避免通过多问问题或重复操作掩盖覆盖缺口。
- 本轮只交付设计文档，不修改运行代码、用户会话或部署；没有运行行为变更测试。

## 2026-09-16（实施：第一阶段最小闭环）

- 计划模型：`PlanStep.observations`（问题 + 有限选项，含 kind=unknown 选项）、`Plan.requires_observations / excluded_by_observations`；库加载时校验条件引用的观察与选项确实被某步骤声明。
- 配置：`rv_power_supply` 升到 v2，两步 expected_result 改为「得到观察结果」，s1 声明 `dock_power_light`、`dock_contacts`，s2 声明 `charging_indication` 并链接已有问诊题「放回基站后，设备有正常的充电指示或充电语音吗？」（yes→indicated，no→none）。没有新增设备操作。
- 契约：`StepFeedbackPayload.observations`、`TroubleshootStep.observations`、`StepCardItem.observation_answers`、`ExecutedStep.observed`、`EscalationReason.cause`；schema 与前端类型已重新生成（`make contracts`）。
- 事实：新增 `app/diagnose/observations.py`——观察写成 issue.facts(kind=observation)，绑定 card/plan/step/input，去重、supersede、unknown 不写、旧卡与非本步骤选项忽略；更正观察事实时重新匹配选项。
- 决策：`decide_next()`（`app/diagnose/decision.py`）按 §3.3 顺序返回 safety_stop / handoff_offer / resolved / ask / step；候选 = plans_ranked ≥ 0.3 的未耗尽计划 + 被观察解锁的计划；已执行步骤、耗尽计划、被观察排除的计划不复发；同一观察最多追问 2 次，用户明确说无法判断后不再问。
- verify：EXHAUSTED 只记账并返回 `reassess`；切换 / 追问 / 人工出口统一由 decide_next 决定。graph 新增 `reassess`、`ask_observation` 节点；步骤反馈中新事实使当前计划被排除时也进入 reassess。
- 结束原因：`next_action` 进入状态与摘要；R2 只作兼容规则码，`reason.text / cause` 显示真实原因（no_supported_followup / knowledge_coverage_missing / observation_unavailable / user_requested_human / burden_prefer_proposal）。结束语如实说明「已完成 X、Y，现有资料没有进一步可执行的排查操作；尚未接入真实转接」。
- 前端：StepCard 渲染观察单选组并随三态反馈提交；SummaryCard 显示真实结束原因、观察结果与人工处理状态（prepared = 已整理记录，尚未接入人工）。
- 验证：后端 874 passed（`tests/test_diagnostic_loop.py` 新增 19 例，含 f30 真实事件入口回放）；前端 212 passed；`make contracts-check` 通过。唯一失败 `test_live_category_only_excludes_sku_docs` 依赖本机 WeKnora，单独重跑通过，与本次改动无关。
- 未做（按设计分阶段）：R1/R1b/R1c 计数上限仍在 verify；guide/retrieve 的其他非安全终止分支尚未集中；真实知识覆盖（第三阶段）未新增任何操作分支。
