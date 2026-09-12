# 40: 凭证识别与 ReceiptCard 字段确认

**What to build:** extract 节点调用 receipt_ocr 视觉任务输出 order_no / channel / purchase_date / amount 的字段、逐字段 confidence 与 unreadable 列表；confirm_fields 发 receipt_card + awaiting_input(confirm_receipt)；ReceiptCard 字段可编辑，confidence < 0.7 标黄，提交 confirm_receipt 带 edited[]；识别失败或全部 unreadable 允许手输或跳过。

**Blocked by:** 39（凭证收集 collect_receipt）

**Status:** ready-for-agent

- [ ] A3 样本订单截图识别出订单号与渠道，低置信字段标黄
- [ ] 用户修改一个字段后 edited[] 含该字段名
- [ ] 全字段 unreadable 时卡片为空可手输
- [ ] receipt_card 不含任何质保结论字段

**设计依据：** 03 §1.8；09 §5.3；08 §5
