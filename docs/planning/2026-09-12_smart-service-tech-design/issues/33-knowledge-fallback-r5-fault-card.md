# 33: 知识降级 R5 与故障卡预加载

**What to build:** 承接票 32 的检索最终结果：真实 no_match 的可选补救未触发 / 失败或第二轮仍无结果时，有 applies_to 匹配的预写计划则按默认顺序执行并标注「按标准排障流程」，否则 escalate(R5)；unavailable 直接走同一业务降级，不触发改写。产品确认后从 sku_fault_cards 预加载约 800 token 故障卡常驻上下文，命中即省一次检索。

**Blocked by:** 32（假设汇总 plans_ranked）

**Status:** done（2026-09-12；步骤卡下发在票 34，本票以 guide_entry 占位进入 guide）

**Owner:** Claude Code B（2026-09-12 认领；`orchestrator/app/faultcards/`、`config/fault_cards.yaml`、graph retrieve 后的降级路由）

- [x] WeKnora 停掉 → A1 仍能进入 guide，前端显示「知识库暂不可用，按标准排障流程」（两库 unavailable → tool_call failed 固定文案；故障卡命中作证据 → synthesize 或 standard_flow → plan_cursor → reply → guide_entry(progress guide)；测试 stage=guide）
- [x] category_only 且无匹配计划 → R5 升级（`_diagnose_outcome`：plans_ranked 为空 → escalate_reason=R5 → escalate 节点摘要 reason R5；测试用只含 sku 专属计划的计划库注入）
- [x] sku_fault_cards seed 与预加载有测试，单次输入 token 不超过 8k（`config/fault_cards.yaml` 5 张卡 230–310 token，>800 启动失败；`make seed WHAT=fault_cards` 已写 5 行；retrieve 按 scope 预加载进状态 `fault_card`，reply 上下文带 `<data kind=fault_card>`；`fit_prompt_budget` 以 8k 估算裁证据，单测覆盖）
- [x] 无任何路径让模型用常识生成假设（代码审查项）（synthesize 在 evidence 为空或路由不可用时不调模型直接 standard_flow；测试用源码断言 + 假模型调用次数）
- [x] 改写模型不可用 / 无效、二次 no_match / unavailable 分别有用计划与无计划两类测试；有计划标明真实来源，无计划走 R5，不能把改写文本当成 evidence（有计划三种路径均 standard_flow 且 plans_ranked 无改写文本；无计划走 R5 见上；第二轮失败时 knowledge_status 保留首轮真实结果）
- [x] 直接命中故障卡而未实际检索时不伪造 no_match 触发改写；不因某个候选计划缺证据再次进入改写循环（改写决策的 has_hits 含故障卡命中 → reason=has_hits；synthesize 丢弃缺证据假设后不回到检索）

**设计依据：** 09 §4、§4.1；03 §1.4.2；07 §7；04 §1

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/faultcards/`（library.py：FaultCard / 渲染 / token 估算 / 命中 / 证据项；store.py：sku_fault_cards 表；runtime.py：进程级库，`HAIKE_FAULT_CARDS=off` 单测默认关闭）；graph.py retrieve 增加预加载与故障卡证据、`_diagnose_outcome()`（evidence / fault_card / standard_flow / escalate R5）、`route_after_retrieve`、`guide_entry` 占位节点与 reply → guide_entry 路由；prompts/reply.py 接 fault_card 段与 flow_note。状态新增 `fault_card`、`fault_card_hits`、`diagnose_outcome`、`plan_cursor`。tests/test_faultcards.py 10 项；后端 297 项通过。与票面差异：故障卡以 YAML 为源、表为 seed 产物，运行时读 L4。
