# 18: 安抚句流式先出与 <data> 包裹

**What to build:** 情绪为焦急 / 愤怒时，第一段可见文本是安抚句并先于任何卡片到达；angry 时后续步骤每步不超两句。所有外部文本（用户输入、检索片段、OCR）进入 Prompt 时包在 data 段并声明非指令。

**Blocked by:** 13（stream 入口与 message 事件）、17（intake 结构化抽取与情绪识别）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（2026-09-12 认领；后端：reassure 节点、prompts 文件化、注入测试）

- [x] A2 话术下安抚句 delta 先于 progress(diagnose) 到达（graph.py 新增 `reassure` 节点：strategy ≠ normal 且路由可用时 intake → reassure → disambiguate；测试断言首个 message 早于 product_card 且其后无 diagnose；真实 DeepSeek：「别着急，我马上帮你处理，明天要用一定优先解决。」先于 product_card 到达）
- [x] Prompt 模板文件化到 prompts 目录并带版本号（`orchestrator/app/prompts/`：system.py PROMPT_VERSION、reply.py REPLY_PROMPT_VERSION；angry 时回复指令附「每个步骤不超过两句」）
- [x] 注入「忽略以上指令」类文本不改变模型输出结构（测试用例）（用户文本与检索片段分别包在 `<data kind=user_message>` / `<data kind=retrieved_snippets>`，`</data>` 被转义；角色层声明 data 段非指令；intake 金标测试含注入样例，结构化输出仍过 schema）

**设计依据：** 05 §6；07 §15；03 §4

**实现记录（2026-09-12，Claude Code B）：** 安抚句走 `reply.stream`（tag=user_visible）一到两句、不给步骤，预算 8 s；平稳情绪不加节点（保持票 05 的 version 断言）。检索片段中的「忽略以上指令」类模式的过滤与记录（07 §15）尚未做，留给票 33 / 45。
