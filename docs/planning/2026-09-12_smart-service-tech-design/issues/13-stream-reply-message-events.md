# 13: stream 入口与 message 事件

**What to build:** ModelRouter.stream 产出用户可见文本的 delta；API 层只透传带 user_visible 标签的调用，映射为 message_start / message / message_end。把 05 票的占位回复换成真实模型流式回复，AssistantBubble 用 react-markdown + sanitize 渲染。

**Blocked by:** 05（会话创建与 SSE 基础流）、10（结构化 invoke：三种输出策略与 Pydantic 校验）

**Status:** ready-for-agent

- [ ] 首个 message delta 在 2 s 内到达（本地测量 first_visible_ms 并记录）
- [ ] internal 调用的 token 不出现在任何事件中（构造一次 internal 调用验证）
- [ ] 消息按 message_id 聚合，前端不拼接不同 message_id
- [ ] Markdown 渲染经过 sanitize，脚本标签被剥离

**设计依据：** 08 §5；03 §6；05 §3
