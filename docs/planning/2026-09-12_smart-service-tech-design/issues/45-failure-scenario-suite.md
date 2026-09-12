# 45: 故障与边界场景巡检脚本

**What to build:** 自动化跑 01 文档 §3.3 列出的边界场景：重复提交同一动作、连续三次无法操作、首句 / 中途 / 图片安全词、错产品凭证、低置信误命中、断网刷新、服务重启恢复、WeKnora 断开、全模型不可用、回放包不符；输出通过 / 失败与延迟指标。

**Blocked by:** 37（rediagnose 中途补充与纠正）、38（取消 run）、41（订单与渠道核对 L1–L6 与 A3 完成）、43（回放模式与录制包）

**Status:** done（2026-09-13，接手会话；stub 全组 29 场景通过，--live 真实 DeepSeek + WeKnora A1 样例通过）

**Owner:** Claude Code（接手会话，2026-09-13）

- [x] 一条命令跑完全部场景并输出报告（`make inspect` / `haike-inspect`：`orchestrator/app/inspection/`（harness / scenarios / report / cli），进程内内存运行时 + 按 task 分脚本的假模型 + 脚本知识适配器，不发网络请求；报告 JSON + Markdown 写 `reports/inspection/`（含 latest.md）；`--group` 选组，`--live URL` 追加真实服务样例）
- [x] 任一场景失败时退出码非零并指出场景名（每行 `[PASS]/[FAIL] 组 场景 耗时 ← 错误`；结束 stderr `FAILED scenarios: …`，退出码 1；test_cli_exit_code_and_group_filter）
- [x] 报告含 first_visible_ms、card_ready_ms、5 并发下的通过率（延迟从运行器 run_metric 结构化日志捕获，与线上口径一致；stub：first_visible p95 17 ms、card_ready p95 23 ms；5 并发 A1 通过率 100%、墙钟 ~30 ms；--live 真实 A1：first_visible 4254 ms、card_ready 5753 ms）
- [x] 结果写入 findings.md 供演示前冻结判定（`<!-- inspection:start/end -->` 固定块覆盖式回填：时间 / git / 模式 / 通过数 / 失败名 / 延迟 / 并发 / 改写开关摘要 / 真实样例 / **冻结判定**；`--no-findings` 可关）
- [x] 覆盖模糊输入、产品歧义、用户纠正、过期按钮、人工请求；两次澄清答复仍不明进入 R7，拒绝动作不推进状态（routing 组 6 场景：vague_input / product_ambiguity / user_correction_and_stale_button（stale_version + stale_card，计数不变）/ request_human_anytime / two_clarifications_then_r7 / rejected_actions_do_not_advance（422 / 409 不调模型、版本与游标不变））
- [x] 改写开关关闭 / 开启分别巡检：正常 no_match 成功补救、空范围、部分库故障、非法改写、第二轮无结果、预算不足、图片补检索争用、恢复 / 取消后晚到结果（rewrite 组 10 场景：决策表九种上下文 + 8 个端到端；late_result_after_cancel 取消 ≤ 1 s 返回、无残留 active run、后续消息正常）
- [x] 报告标记 rewrite_enabled，给出每 run invoke / 检索轮数、额外延迟及 fallback 结果；真实模型语义样例与 stub 路由测试分开，不能以回放成功声称改写质量达标（Markdown「改写开关巡检」表：rewrite_enabled / invoke / rewrite invoke / 检索轮数 / 第二轮延迟 / 回退 / 知识状态 / 决策原因；live 组单独成节并在 findings 里注明「stub 路由测试通过不代表改写 / 回复语义达标」）

**设计依据：** 01 §3.3；03 §1.4.2；09 §1.1、§4.1；04 §3、§5

**场景清单（2026-09-13）：** boundary 12（重复动作 / cannot_do×3→R1b / 首句·中途·图片安全词 R4 / 错产品凭证 order_product_mismatch / 低置信订单 needs_manual_check / 反馈后断网刷新（续接 + 同 action_id 重放）/ 重启孤儿 run 收尾 / WeKnora 断开 standard_flow / 全模型不可用（降级完成 + model_chain_failed 告警）/ 回放包版本不符）；routing 6；rewrite 10；concurrency 1；live 1。差异：stub 模式默认 `HAIKE_FAULT_CARDS=off`（与单测一致，故障卡路径由票 33 单测覆盖）；「服务重启」用新 RunManager reconcile 模拟，不真的重启进程。后端 432 项（新增 10）、ruff 通过。
