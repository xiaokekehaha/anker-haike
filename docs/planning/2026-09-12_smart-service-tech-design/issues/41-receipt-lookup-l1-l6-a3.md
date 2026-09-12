# 41: 订单与渠道核对 L1–L6 与 A3 完成

**What to build:** orders_mock 与 dealers seed；lookup 规则 L1–L6：订单命中须核对 order.sku 与 product_confirmed.sku，低置信未修改字段命中降为 needs_manual_check，未命中订单但渠道在名录 → channel_in_directory；输出 receipt 的 status / verified_facts / conflicts / next_step，文案由规则表给出；summarize 用 escalate.summary 任务润色字段内文本，失败直渲染。不输出质保资格结论。

**Blocked by:** 40（凭证识别与 ReceiptCard 字段确认）

**Status:** ready-for-agent

- [ ] A3：订单未命中、经销商命中 → 摘要 receipt.status=channel_in_directory 与 next_step
- [ ] 上传另一台设备的订单 → order_product_mismatch 并列出 conflicts
- [ ] 低置信订单号恰好命中他人订单且未修改 → needs_manual_check
- [ ] 摘要文本中不出现「可保」「标准质保」等资格结论（字符串断言）

**设计依据：** 09 §5.2；03 §1.8；00 D16
