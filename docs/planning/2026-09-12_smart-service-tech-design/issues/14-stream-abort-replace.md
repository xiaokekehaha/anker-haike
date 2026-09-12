# 14: 流式中断切换：aborted / replaces / model_tier

**What to build:** 主模型流式中途失败时发 message_end(aborted)，降级模型从头生成并以 message_start(replaces) 开始，前端替换旧消息内容；备用模型回复带 model_tier=fallback 并显示「简化回复」标注。

**Blocked by:** 11（降级链与 task 预算）、13（stream 入口与 message 事件）

**Status:** ready-for-agent

- [ ] 注入中途断流后，前端最终只显示一条完整替换后的消息
- [ ] message_end 带 model_tier，前端在 fallback 时显示标注
- [ ] 简化模式 Prompt 变体存在并在 fallback 时使用

**设计依据：** 08 §5；07 §6
