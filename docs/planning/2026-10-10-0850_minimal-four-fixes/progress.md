# 进度

- 08:40 根因分析与归因分类写入 docs/claude 两份 spec；用户确认按 2→1→3→4 做，先提交 Codex 分支
- 08:50 Codex 十轮工作区分四个 commit 入库（568e70d 后端、9ca98e2 测试、f6b4eb9 前端、1fc3a8e 文档）
- 09:00 第 2 项 c785885：streaming.MarkerFilter + product_questions 编号渲染；新测试 10 项
- 09:08 第 1 项 9b658e8：reduce R4 三态（unconfirmed / reported / cleared / disputed）+ SAFETY_CONFIRM_QUESTION；7 项单测 + T23 HTTP 用例
- 09:18 第 3 项 e1ad563：Hypothesis.matched_section / missing_fact；filter precondition_status；_diagnose_outcome 从事实记分支回答；13 项
- 09:24 第 4 项 4cecc95：analytics/outcome.derive_outcome；classify / episode / METRIC_ROWS_SQL 共用；前端 partial_closed 文案；真实 Postgres SQL 用例
- 09:26 ci-local 全绿：后端 1160 passed / 2 skipped，契约 90，前端 230
- 09:28 make up 重建，orchestrator healthy；启动 63 单真实复测
- 09:31 第一轮 63 单复测（reports/eval/20261010T013041Z）：intent 100%、sop 86%、forbid 0。四项目标全部到达：
  T23 不再 R4，走 rv-0138 两步；T53 直落「无法开机」小节 s2，trace 有 question_answered_from_facts；
  T35 正文无 id，analytics 投影 consult_answered；T41 不再重复「没拖地」，改问报错具体文字。
  退步 1 单：T55 补照片一轮 diagnose.synthesize 超预算（authority 10.1k / 7.0k），候选删空 → R5。
- 09:40 根因：非 intake 任务的 authority 把 facts / step_attempts 的存储字段原样喂模型，每条事实约 250 token；
  这是 Codex 十轮前就有的隐患，本轮 T55 多了 2 条症状事实才越线。修 _model_authority 投影（cd872e2），
  同一 checkpoint 回放：删 4 条证据后 6835 token 可入模型。make up 后启动第二轮复测。
- 10:05 第二轮 63 单复测（reports/eval/20261010T020227Z）：intent 100%、sop 86%、forbid 0。T55 恢复 warranty_replace（3 卡 + 服务单）；
  T20 恢复出卡。新暴露 node_failed 2 单（T18 / T23）：CaseConflict「escalated_summary → awaiting_approval」。
  追日志共 48 次、约 20 单同路径：排障走完未解决 + 无订单号 + 跳过凭证 → propose 置 escalated_summary → summarize 调
  hand_off 入队，TRANSITIONS 没这条边。第一轮也有（T40 / T42 当时记 node_failed），1853 终测时同路径但停在 upload_receipt 没触发。
  补迁移边（de95b82）+ T23 真实 HTTP 路径测试。T38 / T40 / T43 的轮次波动是模型 needs_confirmation / 意图读成 product_question，
  不加代码。make up 后启动第三轮。
- 10:20 第三轮 63 单复测（retest-021644）：intent 100%、sop 84%、forbid 0、node_failed 0、CaseConflict 0。四项目标三轮稳定达成；
  sop 波动来自 E 类问句终点（T38 / T40 / T50 轮次变化）。三轮报告归档到本目录 retest-*/，结论写 findings.md。
