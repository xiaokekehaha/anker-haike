# 24: product_state 三分与追问上限 R7

**What to build:** 零命中或用户两次未选中时：有扫地机品类词 → category_only，仅允许 category_generic 知识；否则追问最多 2 次后 escalate(R7 品类不明)。删除「通用扫地机」降级。

**澄清补充（2026-09-12，已实现）：** 按 09 §1.1 在现有 intake / disambiguate 中使用继续 / 澄清 / 升级三种处理结果，增加 checkpoint 内部 clarification.reason / attempts。R7 从品类不明扩展到必要症状缺失或信息冲突，两次澄清答复仍不明时升级；不因高置信度强行路由，也不新增卡片类型。票 37 复用此行为处理多轮纠正。

**Blocked by:** 21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** done（2026-09-12，A 线接手会话）

- [x] 「机器不吸了」→ 追问 → 回答仍不明 → 第二次追问 → 第二次回答仍不明 → R7 升级摘要（单测 + uvicorn/Postgres 实测：v4 → v9 → v14，摘要 reason R7、observations 记录澄清经过）
- [x] 「扫地机不吸了，不知道型号」→ category_only → 进入 diagnose（不追问、不出卡；前提是该品类有 category_generic 预写计划）
- [x] product_state 三值写入状态并出现在摘要（confirmed_sku / category_only / unknown 各有断言；摘要 product 字段按状态渲染）
- [x] 追问文案由 disambiguate.clarify 任务生成，失败用固定文案（tag=internal、结构化 {question}、<data> 包裹；模型失败 / HAIKE_LLM=off 用 FIXED_QUESTIONS）
- [x] 无上下文的「这个又不行了」问一个具体问题；明确上文则承接，不盲目归入吸力异常（产品已确认且更早轮次有故障描述 → 继续；否则 product / symptom 澄清）
- [x] 两次澄清分别收到回答后仍缺信息才触发 R7；仅等待用户不升级；attempts 跨 run / 刷新保留，信息补齐并可继续才重置（clarification 在 checkpoint；attempts 只在真正发问 / 出卡时 +1；确认产品或信息齐全后置 None）
- [x] 品类已知但症状不明走 symptom 澄清，冲突走 conflict；category_only 有适用通用计划时不强求具体型号（conflict = 已确认产品与本轮品类不一致且无法唯一定位；单命中另一型号视为纠正，旧证据失效）
- [x] 澄清阶段不生成新步骤，不运行无命中改写；done(completed) 只结束本 run，不把会话标 solved；失效 pending 卡片从权威状态清除（clarify 节点直接 END；用户不选卡片改发文本时 intake 清空 pending_card，快照 pending_input 为空，旧卡片动作 409 不计次数）

**设计依据：** 01 F5c；09 §1.1、§2.1；03 §1.2、§1.3
