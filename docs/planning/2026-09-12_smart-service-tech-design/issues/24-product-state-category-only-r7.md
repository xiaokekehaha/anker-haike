# 24: product_state 三分与追问上限 R7

**What to build:** 零命中或用户两次未选中时：有扫地机品类词 → category_only，仅允许 category_generic 知识；否则追问最多 2 次后 escalate(R7 品类不明)。删除「通用扫地机」降级。

**Blocked by:** 21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** ready-for-agent

- [ ] 「机器不吸了」→ 追问 → 仍不明 → 第二次追问 → R7 升级摘要
- [ ] 「扫地机不吸了，不知道型号」→ category_only → 进入 diagnose
- [ ] product_state 三值写入状态并出现在摘要
- [ ] 追问文案由 disambiguate.clarify 任务生成，失败用固定文案

**设计依据：** 09 §2.1；03 §1.3
