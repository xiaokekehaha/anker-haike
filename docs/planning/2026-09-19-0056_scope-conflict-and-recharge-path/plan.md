# 问题范围冲突澄清与 A1289 回充路径

起因：会话 37cea3ff86574d05a162adf53bca34d3（分析见 `docs/planning/2026-09-18-20_session-reversibility-review/`）。
用户主诉「给充电宝本身充电很慢」，词表没有槽位被归入 `pb_no_input`；判别题答「连接笔记本时显示 UVP」后，
码内候选全被观察排除、码外计划 `pb_737_laptop_uvp` 被解锁，系统报 `knowledge_coverage_missing` 转人工。
第 3 轮检索已命中回充相关官方资料与工单，但没有对应计划，答案到不了用户。

## 第一性原理约束

1. 用户的话是事实，症状码是假设。假设只影响排序，不能把候选清零；被观察推翻时要能重开范围。
2. 帮助有两种形态：操作步骤与解释。两种都要有来源。
3. 硬约束只有安全、型号适用、资源、已执行；其余都是软的。
4. 一轮做一件事：事实变了才重算候选，没变不重新检索。
5. 结束原因说真话。

## 范围

第一步，内容：

- `config/symptom_taxonomy.yaml`：power_bank 增加故障族「自身回充慢」`pb_slow_input`，两道判别题 yes 侧收录。
- `config/plans.yaml`：新增 `pb_737_recharge_slow`（A1289，来源 `official_anker737_ports#c1/#c2`）；
  `pb_input_check` 症状码补 `pb_slow_input`；证据索引补两条 ports 锚点。
- `config/fault_cards.yaml`：A1289 卡补回充慢条目；通用卡 `pb_input_check` 症状码同步。

第二步，决策收拢（`app/diagnose/decision.py`、`app/sessions/graph.py`、`app/diagnose/synthesize.py`）：

- 症状码不再过滤 synthesize 的允许集合与检索的故障卡集合；只决定顺序（码内优先）。
  无证据降级排序里码外计划置信度 0.2（低于 0.3 门槛），不会在没有证据时被执行。
- `decide_next`：观察解锁、但症状码与已记录范围不相交的计划，不静默执行，返回 `ask / scope_conflict`，
  用问诊的 `symptom_selection` 机制问一次「两种情况都有吗」。用户选了新范围 → 码扩展 → 正常进入；
  只选原范围 → 该计划按 `outside_confirmed_scope` 跳过，不再问。
- `decide_next`：候选按顺序取第一个可行动作（提问或步骤），排在前面的可执行步骤不再被后面计划的问题抢先。
- `retrieve` 记录 `retrieval_basis`（issue_revision + 计划库版本）；事实修订号与计划库都没变时不重新检索，直接 `reassess`。
- 尚缺观察的计划仍要症状码支持才提问（保持 a4c9d63 的规则），避免无关问题。

## 不做

- 换框架、加 agent、放宽安全 / 资源 / 去重、给 `pb_737_laptop_uvp` 补 `pb_no_input`。
- 观测台展示 `next_action.reason`（`frontend/src/admin` 正由另一会话重构，不碰）。
- 症状码从事实字段迁成独立投影、前端「修改回答 / 切换问题」入口、外部业务补偿协议。
- 观察变化后清空 `plans_ranked` 重排：观察由门槛确定性消费，重排只多一次模型调用。

## 验收

- 单元：37cea3 最终状态（codes=[pb_no_input]、观察 laptop_uvp、device=true）→ `ask / scope_conflict`；
  选「都有」→ `step pb_737_laptop_uvp`；只选原范围 → 跳过 `outside_confirmed_scope`，报 `knowledge_coverage_missing`。
- 单元：码内可执行步骤排在缺观察计划之前时返回步骤；反过来仍提问。
- 单元：`normalize("回充很慢", "power_bank")` → `pb_slow_input`；计划库加载通过；每个症状码有计划。
- 单元：`retrieval_basis` 未变 → `reassess`；变了 → `retrieve`。
- HTTP：37cea3 轨迹（难用 → 有的 → 是的很慢[pb_no_input] → 判别卡答 UVP）→ 范围澄清一句、无摘要；
  回「都有」→ 步骤卡 `pb_737_laptop_uvp`。
- HTTP：主诉按 `pb_slow_input` 归类时直接得到 `pb_737_recharge_slow` 的步骤卡，不问屏幕。
- 既有回归：`test_diagnostic_loop.py`、`test_diagnostic_next_action.py`、`test_conversation_observation_deadlock.py`、
  `test_plans.py`、`test_faultcards.py`、`test_diagnose.py` 通过；`make lint` 清零。
