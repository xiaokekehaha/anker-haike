# 21: 产品确认卡片 ProductCard 端到端（A2 前半）

**What to build:** 多命中时发 product_card，前端 ProductCard 展示候选（图、型号、in_scope=false 标「本期不支持」），用户点选发 select_product，apply_action 写入 product_confirmed 与 product_state=confirmed_sku 后进入下一阶段；单命中直接确认不发卡。

**Blocked by:** 20（三段式等待节点与 /actions 基本通路）

**Status:** done（2026-09-12；Codex 补齐等待态输入限制与前后端验证）

- [x] A2 话术：安抚句 → product_card → 选扫地机 → progress(diagnose)
- [x] 单命中路径不出现 product_card 事件
- [x] 卡片点选后置为 disabled 并显示所选项
- [x] 前端 awaiting_input 态下 Composer 只允许对应 kind 输入

**设计依据：** 02 §4.2；05 §3、§6

**前端收尾（Codex，2026-09-12）：** App/Composer 按 pending_input.kind 限制输入；产品、步骤、凭证字段确认等待态禁用普通文本/图片发送，保留对应卡片及请求人工操作。ProductCard 点击后 pendingActionId 禁用连点，完成后按快照显示 selected_sku。A2 安抚先于产品卡由 test_reply_stream 验证，多/单命中与选择后 diagnose 由 test_sessions_actions 验证；前端 App.test 与 Composer.test 覆盖按钮和请求体。本轮相关后端 33 项、前端全量 117 项通过。
