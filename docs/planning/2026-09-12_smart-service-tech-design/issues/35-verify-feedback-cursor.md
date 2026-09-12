# 35: 反馈推进、计数器与计划切换

**What to build:** step_feedback 三态经 apply_action 写入 steps_executed，更新 counters（not_solved → executed+1、cannot_do → skipped+1），按 next_on 推进 plan_cursor；EXHAUSTED 时若下一计划 confidence ≥ 0.3 则切换并跨计划去重相同 instruction_src。verify 无 LLM 参与。

**Blocked by:** 34（步骤卡下发 guide.step 与 CP-pre-step）

**Status:** done（2026-09-13）

**Owner:** Claude Code A（2026-09-12 认领：`app/guide/verify.py` 计数器 / next_on / 切换 / R1 系列）→ 接手会话（2026-09-13 收尾：graph.py apply_action step_feedback 分支、verify 路由、备注 CP-in、测试、真实链路验收）

- [x] 「仍有问题」→ 下一步卡；「无法操作」→ 按 next_on.cannot_do 推进（`apply_feedback` 按 `plan.next_step_id(step_id, feedback)`；图内测试 not_solved s1→s2、cannot_do s1→s2（hair_wrap.s1.cannot_do=s2）；真实链路同）
- [x] 首计划耗尽后自动切到第二计划首步，plans_exhausted+1（`exhaust_plan`：plans_ranked 里下一未耗尽计划 confidence ≥ 0.3 → 首步；< 0.3 或无 → R2。测试：hair_wrap 三步 not_solved → filter_clog，counters executed=3 / plans_exhausted=1；下一计划 0.2 → R2 → escalate(collect_receipt)）
- [x] 相同 instruction_src 的步骤被跳过（prepare_step 用 steps_executed 的 instruction_src 去重；测试：切到 filter_clog 后其 s1（c15，已在 hair_wrap.s2 执行）被跳过直达 s2，`guide_trace` 记 duplicate_instruction_src；真实链路同）
- [x] verify 节点耗时 < 100 ms 且无模型调用（`apply_feedback` 纯规则；测试 200 次平均 < 100 ms，源码断言不含 ModelRouter / invoke；图内 solved 路径断言假模型调用次数不变）

**设计依据：** 03 §1.6；09 §3.3、§3.4

**实现记录（2026-09-13）：**
- `orchestrator/app/guide/verify.py`：`apply_feedback()` 写 `steps_executed`（plan_id / step_id / card_id / title / instruction_src / feedback / note / ts）、counters（solved 不计；not_solved executed+1 advanced+1；cannot_do skipped+1）；CP-verify 上限 R1 executed ≥ 4、R1b skipped ≥ 3、R1c 合计 ≥ 6（判定在推进前，命中即升级）；next_on → DONE 结束 / 下一步 / EXHAUSTED → `exhaust_plan()`（与 guide 节点共用：plans_exhausted+1、切换或 R2）。
- `orchestrator/app/sessions/graph.py`：`apply_action` 新增 `_apply_step_feedback`：`card_results[card_id]={feedback, note?}`；备注先过 CP-in（action_note 含 R4 → 升级，不推进计数）；结果写 `_verify`（瞬态）供 `route_after_apply`：next → guide（出下一张卡）、done → END（结束语流式在票 36）、escalate → escalate 子流程（R1/R1b/R1c/R2 为常规升级，先 collect_receipt）。动作 run 起点刷新 `at`（预算与 card_ready_ms 口径）。结构化日志 `event=cp_verify`（feedback / outcome / rule_id / counters / switched_to）。
- 快照：step_card 折叠带 feedback / note（票 07 已预留），stage 结束时为 verify。
- 测试：`tests/test_guide.py` 17 项（票 34 + 35）；既有 14 个测试文件的「一轮结束 = done(completed)」断言改为 `done(awaiting_input)` + step_card（进入 guide 的路径现在都停在步骤卡）。后端 368 项、前端 121 项通过。
- 真实链路（DeepSeek + WeKnora）：s1 not_solved → s2 卡（v9）；s2 cannot_do → EXHAUSTED → 切 filter_clog，s1 去重跳过 → s2 卡（v12）；solved → done(completed) v14，快照 pending 空、stage=verify。
- 未做（票 36）：solved 结束语流式；R1/R1b 升级摘要含步骤的端到端验收。
