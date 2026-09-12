# 21: 产品确认卡片 ProductCard 端到端（A2 前半）

**What to build:** 多命中时发 product_card，前端 ProductCard 展示候选（图、型号、in_scope=false 标「本期不支持」），用户点选发 select_product，apply_action 写入 product_confirmed 与 product_state=confirmed_sku 后进入下一阶段；单命中直接确认不发卡。

**Blocked by:** 20（三段式等待节点与 /actions 基本通路）

**Status:** ready-for-agent

- [ ] A2 话术：安抚句 → product_card → 选扫地机 → progress(diagnose)
- [ ] 单命中路径不出现 product_card 事件
- [ ] 卡片点选后置为 disabled 并显示所选项
- [ ] 前端 awaiting_input 态下 Composer 只允许对应 kind 输入

**设计依据：** 02 §4.2；05 §3、§6
