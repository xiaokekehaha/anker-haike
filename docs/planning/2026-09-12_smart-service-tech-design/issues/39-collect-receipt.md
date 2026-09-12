# 39: 凭证收集 collect_receipt

**What to build:** 常规升级（R1 / R2 / R6 等非安全路径）进入 escalate 子流程 substage=collect_receipt：awaiting_input(kind=upload_receipt)，Composer 切换为凭证上传（purpose=receipt）并提供「跳过」；skip_receipt 带 reason，跳过后 receipt.status=not_collected 直接 summarize。

**Blocked by:** 25（范围外产品 R8 与 request_human 全局动作）、29（图片上传与会话期存储）

**Status:** ready-for-agent

- [ ] R1 升级后前端出现凭证上传态与跳过按钮，progress 带 substage
- [ ] 跳过 → escalation_summary(receipt.status=not_collected)
- [ ] 在非 upload_receipt 位置上传的图片走 rediagnose 而非凭证
- [ ] 用户提及退换 / 保修（R6）在常规升级时也进入此子流程

**设计依据：** 09 §5.1；05 §2；03 §1.7
