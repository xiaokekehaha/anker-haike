# 34: 步骤卡下发 guide.step 与 CP-pre-step

**What to build:** guide 的 prepare_card 取 plan_cursor 指向的步骤，LLM 只把 instruction_src 原文改写成一句可执行话（不得增删动作，失败用原文）；evidence_ids 必须全部在允许集合内否则丢弃取下一步；CP-pre-step 复查安全词与高危动作 caution；card_id 由 (session, plan, step) 派生；发 step_card，前端 StepCard 显示标题、操作、预期结果、caution、来源角标。

**Blocked by:** 33（知识降级 R5 与故障卡预加载）

**Status:** done（2026-09-13）

**Owner:** Claude Code A（2026-09-12 认领：`app/guide/steps.py` 改写 / 校验 / CP-pre-step、`app/rules/service.py` check_pre_step、`app/prompts/guide.py`、前端 StepCard）→ 接手会话（2026-09-13 收尾：graph.py guide 三段式集成、证据越界校验、预算、测试、真实链路验收）

- [x] A1 首步卡在含图轮 15 s 内就绪（card_ready_ms 记录）（guide 节点写 `card_ready_ms` 到状态并打 `event=card_ready` 结构化日志；真实 DeepSeek + WeKnora 文本轮实测 6.9 s，含 reply 流；图内测试断言 < 15 s）
- [x] 改写结果与原文动作一致（金标对比测试）（`rewrite_is_faithful`：动作词干集合改写前后必须相等且非空；test_guide 金标 5 对：忠实改写接受、增动作 / 少动作 / 无动作拒绝；图内测试：不忠实改写 → 原文，`guide_trace.rewritten=False`）
- [x] 高危步骤无 caution 时被丢弃并取下一步（`RulesService.check_pre_step`：R4 词 → escalate；`pre_step.high_risk_actions` 命中且无 caution → drop；prepare_step 按 next_on.not_solved 取下一步并记 `dropped`；本计划全部丢弃 → `exhaust_plan` 切换或 R2）
- [x] StepCard 同时只有一张「待反馈」，旧卡折叠为一行（Timeline 只把 pendingInput.card_id 的卡置为 active；已答旧卡渲染为一行 + 反馈标签；StepCard.test 4 项）
- [x] EvidenceDrawer 与 StepCard 按 evidence_id 联动高亮（StepCard onHover → Timeline hover state → EvidenceDrawer highlight；测试断言 hover 时对应 li 带 data-highlight 且计数文案正确）

**设计依据：** 03 §1.5；09 §1、§2.5；05 §3

**实现记录（2026-09-13）：**
- `orchestrator/app/guide/steps.py`：`prepare_step()` 循环取步骤：跨计划去重（instruction_src 已执行 → 跳过）→ evidence_ids（同 doc 允许证据 + 命中该计划的故障卡 + diagnose 为该计划给出的 evidence_ids；后者可能越界，越界即丢弃步骤，09 §2.5）→ CP-pre-step → `guide.step` 改写（internal，预算 `min(6 s, 剩余 − 2 s)`，剩余 < 3 s 跳过；失败 / 不忠实 / 超 120 字 → 原文）。`card_id = uuid5(session|plan|step)`。
- `orchestrator/app/sessions/graph.py`：`guide` 节点替换票 33 的 `guide_entry` 占位：写 `pending_card(kind=step_feedback, payload.step)` → `await_input` 发 `step_card`（版本取 langgraph_step，与 awaiting_input / done 一致）→ interrupt。R4 → escalate；本计划耗尽 → `exhaust_plan` 切换 / R2。状态新增 `card_ready_ms`、`guide_trace`（reducer 追加：step_dropped / step_ready / plan_exhausted / verify）。
- `orchestrator/app/prompts/guide.py`（A）：只改写、不增删动作、不加安全提醒、JSON 输出；情绪策略 reassure_and_shorten 时要求更短。
- 前端 `StepCard.tsx`（A）+ `App.tsx` awaiting 提示按 pending kind 细分（step_feedback：「请按步骤操作后，在卡片上告诉我结果」）+ `StepCard.test.tsx`。
- 与票面差异：evidence_ids 的允许集合校验只对 diagnose 输出的 id 真正可能触发（计划步骤自身证据来自已审核的 plans.yaml 索引，天然在集合内）；改写「失败用原文」时 model_trace 记 `model_used=skipped`。
- 真实链路（DeepSeek + 本机 WeKnora，uvicorn :8010）：A1 文本 → 检索 10 条 → 回复流 → `step_card`(hair_wrap s1, evidence_ids 6 条含故障卡) → `awaiting_input(step_feedback)`；改写模型返回与原文一致的句子，被接受。
