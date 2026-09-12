# 发现

- App 未传 Composer purpose，等待 upload_receipt 时上传仍使用默认 fault；没有跳过入口，状态文案总是要求在上方卡片选择。
- Composer 不区分 select_product/confirm_receipt 等 pending kind；ReceiptCard 已存在，但缺少针对字段/快照生命周期的测试。
- guide.step 配置仍为四项，chain_max=3；上轮记录的全局 lint 三项仍待修复。
- 当前票 34–36 仍由 Claude A 认领，本轮不实现其步骤闭环。
