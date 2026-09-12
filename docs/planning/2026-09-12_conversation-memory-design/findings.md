# 核查发现

## 已确认
- 当前架构为 FastAPI + LangGraph + ModelRouter + WeKnora，已有会话执行契约（08）和计划/规则/知识契约（09）。
- 原设计任务完成，但实现按票推进；不能以设计完成推断多轮上下文已经实现。
- 工作树已有会话图、模型路由、知识检索等未提交变更；本任务以读取时的当前代码为准，保留这些修改。
- 当前任务只做本地核查与设计补充，不访问数据库。

## 待核对
- 是否有同会话自由文本追问入口，是否把历史传到模型。
- 会话状态持久化与模型语义记忆是否一致。
- 用户身份、长期记忆、摘要、纠错和遗忘机制是否存在。

## 代码与设计差距
- 02 §4.4、07 §2/§4 约定最近 6 轮、状态摘要和输入预算；07 §5 明确本期不做跨会话长期记忆。
- runner.run_message 用 session_id 作为 thread_id，runtime 使用 AsyncPostgresSaver；这提供状态恢复基础。
- graph.intake 累积用户 messages；回复累积到 visible_messages；intake / reply 的 Prompt 仅构造 system + 本轮 human，没有读这些历史。
- intake 每轮直接覆盖 symptoms/product_hints，抽取失败也会把空列表写回；短追问可能丢掉已知症状。
- disambiguate 遇到 product_confirmed 立即返回，尚无自由文本纠正产品的专门处理。
- reply 使用累计 evidence 的前 6 条；没有独立当前轮证据集合，后续检索可能被早期证据挤占。
- App.tsx 的 CHAT_OFFLINE=true，当前前端尚不能端到端发送追问。
- 待以纯内存验证上述信息缺失；不调用远程模型，不启动数据库生命周期。

## 一手文档核对
- LangChain Memory overview 区分 thread-scoped checkpoint 与跨会话 namespace store，并明确需要管理送入模型的消息和长上下文；支持本次对存储与模型上下文的区分。
- 来源：https://docs.langchain.com/oss/python/concepts/memory （2026-09-12 读取）。
- DeepSeek context caching 页面首次读取出现 Internal Error，后续改用官方搜索定位。

## 验证结果
- probe_current_behavior.py 纯内存复现：用户历史已累积 2 条，但 intake 没收到上轮用户文本，reply 没收到上轮助手文本；空抽取把「吸力下降」覆盖为 []；已确认 X9 Pro 后输入「说错了，是 S1 Pro」仍保留 X9 Pro；累计 6 条旧证据后，第 7 条新证据不进入主/备 Prompt。
- 选定现有测试：34 passed、1 failed、4 deselected（排除真实 DeepSeek）。失败项 test_internal_tokens_never_enter_events_and_ids_aggregate：假主模型 calls[0].tags 为空，未满足 user_visible 断言；没有改代码掩盖失败，尚不能据此推断生产流泄漏。
- DeepSeek 官方缓存文档已定位：https://api-docs.deepseek.com/guides/kv_cache/；同前缀命中用于计算复用，不能替代业务层记忆读取与上下文构造。
