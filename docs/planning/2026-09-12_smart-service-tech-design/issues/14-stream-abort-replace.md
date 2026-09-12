# 14: 流式中断切换：aborted / replaces / model_tier

**What to build:** 主模型流式中途失败时发 message_end(aborted)，降级模型从头生成并以 message_start(replaces) 开始，前端替换旧消息内容；备用模型回复带 model_tier=fallback 并显示「简化回复」标注。

**Blocked by:** 11（降级链与 task 预算）、13（stream 入口与 message 事件）

**Status:** done（2026-09-12；reducer 按 replaces 替换、fallback 标「简化回复」随前端集成完成）

**Owner:** Claude Code B（2026-09-12 认领；后端：aborted / replaces / model_tier 与简化模式 Prompt 变体；前端替换与「简化回复」标注建议 Codex 认领）

- [x] 注入中途断流后，前端最终只显示一条完整替换后的消息（后端：假模型在第二个 token 后抛错 → message_end(aborted) → 新 message_start(replaces=旧 id) → 完整文本 → message_end(completed, fallback)；快照 timeline 只剩一条替换后的 assistant_message。前端 reducer 替换逻辑待 Codex）
- [x] message_end 带 model_tier，前端在 fallback 时显示标注（后端 completed / aborted 均带 model_tier；tier 以「第一家真正发请求的模型」为 primary，路由前因未配置被跳过的不算；前端标注待 Codex）
- [x] 简化模式 Prompt 变体存在并在 fallback 时使用（`SIMPLIFIED_LAYER` 追加为系统提示第四层；`reassurance_messages` / `reply_messages` 同时返回主 / 简化两套，测试断言备用模型收到简化层而主模型没有）

**设计依据：** 08 §5；07 §6

**实现记录（2026-09-12，Claude Code B）：** 主模型未吐字即失败 → 按 invoke 同款规则同模型退避重试（对前端不可见）；已吐字后失败 → aborted + switched，降级模型用简化变体从头生成，`uuid_for_replacement()` 派生稳定的新 message_id；整链耗尽 → 最后一条 message_end(aborted)，run 仍以 done(completed) 结束。
