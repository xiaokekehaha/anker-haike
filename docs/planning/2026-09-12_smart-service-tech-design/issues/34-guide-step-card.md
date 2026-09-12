# 34: 步骤卡下发 guide.step 与 CP-pre-step

**What to build:** guide 的 prepare_card 取 plan_cursor 指向的步骤，LLM 只把 instruction_src 原文改写成一句可执行话（不得增删动作，失败用原文）；evidence_ids 必须全部在允许集合内否则丢弃取下一步；CP-pre-step 复查安全词与高危动作 caution；card_id 由 (session, plan, step) 派生；发 step_card，前端 StepCard 显示标题、操作、预期结果、caution、来源角标。

**Blocked by:** 33（知识降级 R5 与故障卡预加载）

**Status:** ready-for-agent

- [ ] A1 首步卡在含图轮 15 s 内就绪（card_ready_ms 记录）
- [ ] 改写结果与原文动作一致（金标对比测试）
- [ ] 高危步骤无 caution 时被丢弃并取下一步
- [ ] StepCard 同时只有一张「待反馈」，旧卡折叠为一行
- [ ] EvidenceDrawer 与 StepCard 按 evidence_id 联动高亮

**设计依据：** 03 §1.5；09 §1、§2.5；05 §3
