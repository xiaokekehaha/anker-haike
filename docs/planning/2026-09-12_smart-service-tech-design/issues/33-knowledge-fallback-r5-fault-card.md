# 33: 知识降级 R5 与故障卡预加载

**What to build:** 检索 no_match 或 unavailable 时：若存在 applies_to 匹配的预写计划则按默认顺序执行并标注「按标准排障流程」，否则 escalate(R5)。产品确认后从 sku_fault_cards 预加载约 800 token 故障卡常驻上下文，命中即省一次检索。

**Blocked by:** 32（假设汇总 plans_ranked）

**Status:** ready-for-agent

- [ ] WeKnora 停掉 → A1 仍能进入 guide，前端显示「知识库暂不可用，按标准排障流程」
- [ ] category_only 且无匹配计划 → R5 升级
- [ ] sku_fault_cards seed 与预加载有测试，单次输入 token 不超过 8k
- [ ] 无任何路径让模型用常识生成假设（代码审查项）

**设计依据：** 09 §4；07 §7；04 §1
