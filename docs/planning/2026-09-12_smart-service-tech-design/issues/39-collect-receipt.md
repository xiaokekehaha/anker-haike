# 39: 凭证收集 collect_receipt

**What to build:** 常规升级（R1 / R2 / R6 等非安全路径）进入 escalate 子流程 substage=collect_receipt：awaiting_input(kind=upload_receipt)，Composer 切换为凭证上传（purpose=receipt）并提供「跳过」；skip_receipt 带 reason，跳过后 receipt.status=not_collected 直接 summarize。

**Blocked by:** 25（范围外产品 R8 与 request_human 全局动作）、29（图片上传与会话期存储）

**Status:** backend-done（2026-09-12，A 线接手会话；前端凭证上传态 / 跳过按钮待 Codex 在票 06 之后接入）

- [ ] R1 升级后前端出现凭证上传态与跳过按钮，progress 带 substage（后端已就位：progress(escalate, collect_receipt) → awaiting_input(kind=upload_receipt) → done(awaiting_input)，快照 pending_input.kind=upload_receipt、substage=collect_receipt，无卡片事件；前端 Composer 按 kind 切换为 purpose=receipt 上传并提供「跳过」，待票 06）
- [x] 跳过 → escalation_summary(receipt.status=not_collected)（skip_receipt{reason} 经 apply_action 写 receipt.status=not_collected + skipped_reason，card_results 记录；直接 summarize，next_step「请准备购买凭证，人工协助核实」；reason 非法 422、等待凭证时发 select_product 409 not_allowed_now）
- [x] 在非 upload_receipt 位置上传的图片走 rediagnose 而非凭证（intake 只在 pending_card.kind=upload_receipt 且本 run 有 purpose=receipt 图片时建立 receipt；其他位置的凭证图按普通消息处理，不建 receipt 状态、不进读图（vision 只看 fault）；rediagnose 语义本身在票 37）
- [x] 用户提及退换 / 保修（R6）在常规升级时也进入此子流程（R6 为 flag 不单独升级；随后的常规升级进入 collect_receipt，摘要 reason 保留触发规则、next_step 指向凭证）

**设计依据：** 09 §5.1；05 §2；03 §1.7

**实现记录（2026-09-12，A 线接手会话）：** `app/sessions/receipt.py`（分流集合、receipt 状态构造、摘要 ReceiptOutcome 派生）；graph.py：原 escalate 节点改名 summarize，新 escalate 入口节点 + route_escalate 分流（summarize / prepare_receipt / receipt_extract），prepare_receipt 复用 await_input 三段式（kind=upload_receipt，无卡片事件），apply_action 增 skip_receipt，intake 增等待凭证时的上传识别；build_summary 的 receipt 改为从 state.receipt 派生。上传后的 extract 为票 40 前的占位（status=needs_manual_check、「凭证已收到，待人工核实」）。
**分流决定：** 直接摘要（不收凭证）= R3 人工请求、R4 安全、R5 无可用知识、R7 品类不明、R8 范围外；09 §5.1 只列了 R4 / request_human，R5 / R7 / R8 是本票补充（凭证对这三类无助于处理，且 R7 / R8 没有可核对的受支持产品），已记 findings，需回填 09。测试 tests/test_sessions_receipt.py 7 项。
