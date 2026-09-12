# 发现

- 接续时 HEAD 9413c3f；共享树大量既有未提交代码，票 41 已由其他 Codex 会话完成。
- App 没有向 Composer 传 pending kind/purpose，也没有 upload_receipt 跳过入口；默认 purpose=fault 无法触发后端凭证收集。
- Composer 不区分产品/步骤/字段确认等待态，允许任意消息；图片处理中的异步结果未在卸载/切换时隔离。
- ReceiptCard 只在首次渲染复制 item.fields，后续 confirmed_fields 或同卡快照更新不反映在输入框，易显示旧 OCR 值。
- 全量后端回归已有 guide.step 四模型链超过 chain_max=3 的阻塞记录，本轮先验证前端与相关凭证 API。
- 后端 /messages text 必填且 min_length=1；前端纯图片统一补准确说明，避免 422。
- 原 image 上传成功后只有本地文本气泡；补图片完成后快照同步，使用服务器 image_ids/images 显示附件。
- 所有本轮 A3 模拟 SSE 均先通过生成 schema 验证，避免非法事件静默跳过导致假阳性。
