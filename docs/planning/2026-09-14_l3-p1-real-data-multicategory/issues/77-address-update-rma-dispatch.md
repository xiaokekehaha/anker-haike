# 77: address.update 与 rma.dispatch 动作

**What to build:** `address.update`（write：参数 order_no + 新地址结构化字段；前置：订单未发货；用户确认卡展示新旧地址；模拟后端 `update_address`）；`rma.dispatch`（write：为已批准的 repair 方案创建取件 / 送修单，参数取件地址 + 时间窗；模拟后端 `create_rma`，状态 scheduled → picked → repairing → returned）；`consult` 增 `address_update` 意图参数抽取（地址字段用 interpret facts，不用正则）；`track` 支持 RMA 状态句；两动作均 `auto_allowed` 由政策决定（address 默认 true 当未发货；rma 默认 true 当 repair eligible）。

**Blocked by:** P0 57, 58；P1 74

**Status:** todo

**Owner:** —

- [ ] 已发货订单改地址 → 政策拒绝 + 条款 + 人工选项
- [ ] RMA 全状态在 track 中可见；用户「修好了吗」走 consult 读状态
- [ ] 地址不在日志明文（privacy 补地址已在票 48，回归）

**设计依据：** 03 §2、§5；00 D-L3-9
