# 记录

- 2026-10-09 15:40 读测评文档；三个探索子任务核对 interpret/synthesize/qa_index/plans/guide、契约与前端卡片、tasks/l3/graph/summary。
- 15:50 逐条看首测轨迹 T11/T18/T22/T30/T31/T34/T50/T52/T60/T61/T51/T9：T31 未进检索即 R2；T18/T22/T30 命中正解文档后被 applicability 门槛丢弃；T11 的 R3 来自 push 字段引文；T51 过保分支硬编码 done。
- 16:05 写 findings.md、plan.md。未改代码，未提交。
- 16:12 ci-local 全绿；提交 fbefd7a（今日两轮代码）与 bf29496（测评报告与方案）。
- 16:33 用户要求结合 Codex 复核先出开发规格，只取重点：写 docs/claude/spec_2026-10-09-1633_official-63-remediation.md，第一批详细、二三批概要。未改代码。
- 16:38 新建分支 feat/official-63-remediation（自 bf29496）。开始第一批，TDD：先写失败测试再实现。
- 16:40 §1 事实模型：FactCandidate 加 subject / polarity / timing / action_taken；reduce 判定引文来源（device_message_spans），R3 引文落在推送字段且原文有故障 → report_problem；negated 不进 symptoms；action_taken 压制 operation_update；降级解释同样过来源判定。T11 端到端出 qa_rv_0481 首卡。
- 16:44 §2 适用性：精确同码唯一命中（steps / answer）直通 plans_ranked，不经模型；synthesize 输入结构化事实与错误码，filter_hypotheses 做极性 / 时机 / 对象 / 异码确定性核对并产出澄清；澄清不问已知码。retrieval_basis 加 sku（型号纠正作废旧候选）。
- 16:46 误执行了一次 git stash（含其他会话未提交文档），立即 stash pop 恢复，工作区无损。
- 16:52 §3 首轮 operation_changed 且无候选 → disambiguate；§4 no_match 且无确定症状 → 症状澄清，与 disambiguate 共用同一预算（clarify_subject），问满两次才 R5；预算只在检索有结果时清零。
- 16:58 §5 过保 / 非授权经销商走 advance_tasks（remedy_closed），队列有排障任务时追加一句继续排查。
- 17:05 §6 契约 HandoffBusiness / PendingRequest，make contracts；摘要 problem 回退链、login_country、handoff_business；advance_tasks 在交接后查询完成且已知事实变化时重写交接摘要（T9 两条摘要）；前端 SummaryCard 业务四行。
- 17:10 §7 评测标签 T46 / T50 / T52 / T61；驱动器 done_with_pending_tasks、r3_from_device_text、first_card_forbidden；节点摘要带 human_request_source。
- 17:14 intake schema 超 2560 token 上限：精简新字段描述与提示词后恢复。ci-local 全绿：898 passed、契约 90、前端 226。未提交。
