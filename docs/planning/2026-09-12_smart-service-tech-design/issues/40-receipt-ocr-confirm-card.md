# 40: 凭证识别与 ReceiptCard 字段确认

**What to build:** extract 节点调用 receipt_ocr 视觉任务输出 order_no / channel / purchase_date / amount 的字段、逐字段 confidence 与 unreadable 列表；confirm_fields 发 receipt_card + awaiting_input(confirm_receipt)；ReceiptCard 字段可编辑，confidence < 0.7 标黄，提交 confirm_receipt 带 edited[]；识别失败或全部 unreadable 允许手输或跳过。

**Blocked by:** 39（凭证收集 collect_receipt）

**Status:** done（2026-09-13；票 42 拿到智谱 key 后补跑真实视觉 OCR：合成订单图 15 张 × 3 遍两家均 100%/100%，并跑通真实服务端到端 A3）

- [x] A3 样本订单截图识别出订单号与渠道，低置信字段标黄（2026-09-13 真实视觉模型验收：bake-off 的 15 张合成订单图（含模糊 / 缺字段 / 英文 / 注入标题）× 3 遍，deepseek-flash 与 zhipu/glm-4.6v 均 Schema 100% / 字段 100%；真实服务端到端 A3：上传订单截图 → OCR 1.3 s → receipt_card 四字段全对、逐字段置信度 0.97–0.98 → 确认后 L1–L6 判 order_verified。失效切换下由 glm-4.6v 服务，四字段同样全对（置信度 1.0）。前端 < 0.7 标黄逻辑与手输在票 40 前端部分已有测试覆盖）
- [x] 用户修改一个字段后 edited[] 含该字段名（confirm_receipt{fields, edited} → apply_action 写 receipt.fields / edited，card_results 记 confirmed_fields + edited，快照 receipt_card 项带 confirmed_fields；确认后进入摘要，status 由票 41 lookup 决定，本票占位 insufficient / needs_manual_check）
- [x] 全字段 unreadable 时卡片为空可手输（OCR 全 unreadable、识别失败或无视觉模型：字段 None、confidence 0、unreadable 全字段，卡片仍发出；用户手输后 confirm_receipt 正常写入；也可 skip_receipt → needs_manual_check（凭证图已在））
- [x] receipt_card 不含任何质保结论字段（事件只有 card_id / version / fields / confidence / unreadable，契约 extra=forbid；OCR schema 也只抄录四字段与置信度，提示词禁止判断在保 / 退换）

**设计依据：** 03 §1.8；09 §5.3；08 §5

**实现记录（2026-09-12，A 线接手会话）：** `app/sessions/receipt.py` 增 ReceiptOcr schema、extract_receipt（图片按链上 max_images 只取最新几张，失败 / 无视觉 → 空字段全 unreadable）、card_payload / confirmed_receipt / skipped_after_upload；graph.py：receipt_extract 真接 OCR + tool_call(warranty.receipt_ocr) 并写 pending_card(confirm_receipt) → await_input 发 receipt_card → apply_action 处理 confirm_receipt 与确认阶段的 skip_receipt。tests/test_sessions_receipt_card.py 6 项 + 票 39 上传用例改为「到确认卡」。

**前端收尾（Codex，2026-09-12）：** ReceiptCard 支持低置信字段标黄、未识别提示、四字段编辑、仅提交实际修改的 edited[]。同卡相同字段重放保留草稿，权威版本/字段改变时重建编辑器；confirmed_fields 优先显示，历史卡禁用操作。App 模拟 HTTP/SSE A3 已串到票 41 的订单核对摘要，所有模拟事件在发出前经过生成的 schema 校验。凭证相关后端 39 项、前端全量 117 项、构建、契约与 6 项生成器测试通过。真实图片识别质量仍保留未勾选，模拟链路不代替真实视觉模型验收。
