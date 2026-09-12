# 40: 凭证识别与 ReceiptCard 字段确认

**What to build:** extract 节点调用 receipt_ocr 视觉任务输出 order_no / channel / purchase_date / amount 的字段、逐字段 confidence 与 unreadable 列表；confirm_fields 发 receipt_card + awaiting_input(confirm_receipt)；ReceiptCard 字段可编辑，confidence < 0.7 标黄，提交 confirm_receipt 带 edited[]；识别失败或全部 unreadable 允许手输或跳过。

**Blocked by:** 39（凭证收集 collect_receipt）

**Status:** backend-done（2026-09-12，A 线接手会话；ReceiptCard 前端待 Codex；真实订单截图识别待票 42 有视觉模型 key）

- [ ] A3 样本订单截图识别出订单号与渠道，低置信字段标黄（后端：warranty.receipt_ocr internal 视觉调用输出 fields / 逐字段 confidence / unreadable，receipt_card 带 confidence，< 0.7 由前端标黄；假 router 回放的 A3 样本验证通过，真实截图待票 42；前端 ReceiptCard 待 Codex）
- [x] 用户修改一个字段后 edited[] 含该字段名（confirm_receipt{fields, edited} → apply_action 写 receipt.fields / edited，card_results 记 confirmed_fields + edited，快照 receipt_card 项带 confirmed_fields；确认后进入摘要，status 由票 41 lookup 决定，本票占位 insufficient / needs_manual_check）
- [x] 全字段 unreadable 时卡片为空可手输（OCR 全 unreadable、识别失败或无视觉模型：字段 None、confidence 0、unreadable 全字段，卡片仍发出；用户手输后 confirm_receipt 正常写入；也可 skip_receipt → needs_manual_check（凭证图已在））
- [x] receipt_card 不含任何质保结论字段（事件只有 card_id / version / fields / confidence / unreadable，契约 extra=forbid；OCR schema 也只抄录四字段与置信度，提示词禁止判断在保 / 退换）

**设计依据：** 03 §1.8；09 §5.3；08 §5

**实现记录（2026-09-12，A 线接手会话）：** `app/sessions/receipt.py` 增 ReceiptOcr schema、extract_receipt（图片按链上 max_images 只取最新几张，失败 / 无视觉 → 空字段全 unreadable）、card_payload / confirmed_receipt / skipped_after_upload；graph.py：receipt_extract 真接 OCR + tool_call(warranty.receipt_ocr) 并写 pending_card(confirm_receipt) → await_input 发 receipt_card → apply_action 处理 confirm_receipt 与确认阶段的 skip_receipt。tests/test_sessions_receipt_card.py 6 项 + 票 39 上传用例改为「到确认卡」。
