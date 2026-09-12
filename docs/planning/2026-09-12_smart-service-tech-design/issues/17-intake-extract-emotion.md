# 17: intake 结构化抽取与情绪识别

**What to build:** intake 节点一次 internal 调用同时输出情绪三级标签 + strategy、product_hints、symptoms、wants_human；strategy 写入状态并注入系统提示三层中的第二层。抽取失败视为 calm、hints 为空。

**Blocked by:** 10（结构化 invoke：三种输出策略与 Pydantic 校验）、15（规则服务骨架与 CP-in 安全升级）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（`orchestrator/app/intake/`、`app/prompts/`、`app/models/runtime.py`；graph.py intake 节点追加抽取）

- [x] 对 A1 / A2 / A3 演示话术抽取结果与预期一致（fixtures 金标）（`orchestrator/tests/fixtures/intake_golden.yaml` 4 条：A1 平稳 + 扫地机线索、A2 焦急 + S1 Pro、A3 愤怒 + wants_human、无产品闲聊；假 router 回放校验映射 4/4；真实 DeepSeek 跑金标 2/4 通过、2 条因当时连接错误跳过（模型不可用即 skip，不算失败）。fixtures 放在 orchestrator/tests 下而非 contracts/fixtures（后者归票 04 / Codex））
- [x] wants_human=true 等价于 R3 命中（写 safety_flags `{rule_id: R3, source: intake, term: wants_human}` 并设 escalate_reason=R3，走与规则命中相同的 escalate 路径；图内测试断言）
- [x] 系统提示三层结构：固定角色、每轮情绪策略、每轮状态摘要（`app/prompts/system.py`：ROLE_LAYER 固定且不含 session / 时间戳以便前缀缓存并声明 <data> 非指令；`emotion_layer(strategy)`；`state_layer(summary)` 键序固定；`wrap_data()` 包裹用户文本并转义 </data>；PROMPT_VERSION=2026-09-12.1）
- [x] 抽取失败走降级不阻断流程（路由不可用 / 链耗尽 / 容量满 / 空文本 → calm·normal、hints/symptoms 空、wants_human=false，model_trace 记 `intake: skipped`；单测与 HAIKE_LLM=off 默认路径均覆盖）

**设计依据：** 03 §1.1、§1.2、§4

**实现记录（2026-09-12，Claude Code B）：** `app/intake/extract.py`（IntakeExtraction schema：emotion_level / product_hints / symptoms / wants_human；strategy 由 level 规则映射 calm→normal、anxious→reassure_first、angry→reassure_and_shorten，不信任模型给的策略；task=intake，tag=internal，预算 6 s）；`app/models/runtime.py` 进程级 Router（main.py lifespan 注入；`HAIKE_LLM=off` 时返回 None，单测默认）；graph.py intake 节点在 CP-in 未命中后调用，写 emotion / product_hints / symptoms / model_trace。真实端到端：「我的 eufy X9 Pro 扫地机不吸了，滚刷那儿缠了好多头发，急死了明天要用」→ DeepSeek 抽出 level=anxious、hints=[eufy X9 Pro, 扫地机]、symptoms=[不吸了, 滚刷缠头发]。与票面差异：strategy 注入第二层已实现于 compose_system_prompt，但 reply.stream 安抚句（票 18）尚未接入，当前只有 intake 自身调用使用该提示。
