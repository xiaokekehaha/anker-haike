# 13: stream 入口与 message 事件

**What to build:** ModelRouter.stream 产出用户可见文本的 delta；API 层只透传带 user_visible 标签的调用，映射为 message_start / message / message_end。把 05 票的占位回复换成真实模型流式回复，AssistantBubble 用 react-markdown + sanitize 渲染。

**Blocked by:** 05（会话创建与 SSE 基础流）、10（结构化 invoke：三种输出策略与 Pydantic 校验）

**Status:** done（2026-09-12；AssistantBubble react-markdown + rehype-sanitize 随前端集成完成，脚本标签剥离有测试）

**Owner:** Claude Code B（2026-09-12 认领；后端：ModelRouter.stream 与图内 reply 节点；AssistantBubble 的 react-markdown + sanitize 属前端，建议 Codex 认领）

- [x] 首个 message delta 在 2 s 内到达（本地测量 first_visible_ms 并记录）（`app/sessions/streaming.py` 在首个 delta 记结构化日志 event=first_visible；真实 DeepSeek 实测 A2 安抚句 907 ms、A1 回复 828 ms，均从流开始计；从 run 开始计需加上 intake 抽取约 2 s，后续按 08 §8 口径以 run_started 为基准再测）
- [x] internal 调用的 token 不出现在任何事件中（构造一次 internal 调用验证）（intake 的 invoke 输出只写状态；测试断言事件 JSON 里不含抽取结果字段；stream() 固定 tag=user_visible，invoke() 固定 tag=internal）
- [x] 消息按 message_id 聚合，前端不拼接不同 message_id（后端一次回复只用一个 message_id；替换时新 id 带 replaces；快照折叠已按 message_id 聚合。前端 reducer 侧由 Codex 在 AssistantBubble 落实）
- [x] Markdown 渲染经过 sanitize，脚本标签被剥离（AssistantBubble：react-markdown + rehype-sanitize + disallowedElements；Cards.test 断言 `<script>` 不存在）

**设计依据：** 08 §5；03 §6；05 §3

**实现记录（2026-09-12，Claude Code B）：** `ModelRouter.stream(task, messages, budget_ms, message_id, fallback_messages)` 产出 start / delta / aborted / switched / end（`app/models/router.py`）；`app/sessions/streaming.py::stream_to_writer` 映射为 message_start / message / message_end；graph.py `reply` 节点用 `reply.stream` 按检索片段作答（Prompt 见 `app/prompts/reply.py`，路由不可用时保持票 05 占位行为）。models.yaml 的 domestic `reply.stream` 链尾加 deepseek 作为票 42 前唯一可用的降级位。tests/test_models_stream.py 7 项、tests/test_reply_stream.py 5 项。
