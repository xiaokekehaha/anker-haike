# 实施记录与偏差

## 与 plan.md 的偏差

1. **降级排序不设 0.2 档。** plan 写「无证据降级排序里码外计划置信度 0.2」。实测它打破了票 19 的 R5 出口：
   `_diagnose_outcome` 看到非空 `plans_ranked` 就进 guide，X9 Pro「找不到基站」从 R5「没有可用计划」变成 R2。
   没有证据时唯一线索就是症状码，`default_plans_ranked` 保持按码过滤；只有模型 + 证据时允许集合才不按码过滤。
   观察解锁的计划不经过排序，范围澄清不受影响。
2. **power_bank 问诊顺序变了。** 加入「自身回充慢」后两道判别题的最小分裂从 2/2 变成 2/3，
   `select_discriminator` 先问「问题出现在给充电宝本身充电的时候吗」再问「有输出反应吗」。
   方向问题先于输出问题，与本次分析「问题范围先明确」一致，接受；两处 HTTP 回归改为两个「没有」。
3. **码内可执行步骤先于范围问题。** 37cea3 状态下若 `plans_ranked` 里有回充计划，先下发回充步骤（它就是对主诉的回答），
   码内路径走完才问范围。纯复原的 37cea3 最终状态（plans_ranked 只有两个输出侧计划）仍直接得到范围问题。

## 已实施

- 词表 `2026-09-19.1`：power_bank 新增 `自身回充慢 / pb_slow_input`，表达式只收带自身回充语境的说法，裸「很慢」交给模型。
- 计划库 `2026-09-19.1`：`pb_737_recharge_slow`（USB-C1 + PD 充电器；官方回充时间参考），
  `pb_input_check` v3 加 `pb_slow_input`；证据索引补 `official_anker737_ports#c1/#c2`（doc_version 取自 kb_manual 文档）。
- 故障卡：A1289 与通用卡同步。
- `decide_next`：`scope_question` 生成 symptom_selection 问题；观察解锁且症状码不相交的计划返回 `ask / scope_conflict`；
  同一题答过后按 `outside_confirmed_scope` 跳过；候选按顺序取第一个可行动作。
- `ask_observation`：`scope_conflict` 分支写 `symptom_interview.question`（带 question_id），走问诊受理路径；
  「都有 / 1 / 2」由 `symptom_question_answer` 确定性解析。
- `_synthesize_step` / retrieve 故障卡过滤：允许集合不按码过滤，码内排前。
- `retrieve` 写 `retrieval_basis`；`_after_product` 在事实修订号与计划库版本都没变时走 `reassess`；
  `route_after_disambiguate` / `route_after_apply` 增加 `reassess` 出边。

## 验证

- `orchestrator/tests/test_conversation_scope_conflict.py` 8 项：37cea3 最终状态 → `scope_conflict`；
  「都有」→ `pb_737_laptop_uvp`；只选原范围 → `outside_confirmed_scope` + `knowledge_coverage_missing`；
  词表 / 计划 / 问诊选项；`_after_product` 短路；HTTP 全程（充不进 → 判别卡答 UVP → 回充 s1/s2 → 范围问题 → 都有 → UVP 步骤，
  观察与反馈不触发检索、范围扩展触发检索、全程无摘要）；HTTP 回充慢直达回充步骤。
- 更新既有回归：`test_diagnostic_loop.py`（静默解锁改为先问范围；新增顺序用例）、`test_diagnose.py`、`test_faultcards.py`、
  两处 power_bank HTTP 问诊顺序。
- 相关文件测试与 `make lint` 结果见 progress.md。

## 未做

- 观测台显示 `next_action.reason`：`frontend/src/admin` 正由另一会话重构。
- 浏览器走查：本机 8000 是旧镜像，按约定不主动重建 docker；HTTP 回归已走真实图与 SSE 事件。
