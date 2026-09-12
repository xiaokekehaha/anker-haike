# 32: 假设汇总 plans_ranked

**What to build:** 文本 query 检索与读图并行；图片新增信息与可选无命中改写共享一次补检索名额，每 run 最多两轮。synthesize 任务（强推理档）输出最多 3 个假设，每个必须引用当前允许集合内的 plan_id 与 evidence_ids，无对应计划的假设丢弃；写入 plans_ranked 与 retrieval_trace。

**查询补充（2026-09-12，待实现）：** 按 03 §1.4.1 扩展现有 `orchestrator/app/sessions/graph.py::retrieval_query`：用已确认产品 / 品类与有效症状构造查询；抽取失败回退到当前原文，scope 仍由产品状态决定。按 §1.4.2 实现默认关闭的 `query_rewrite.enabled`，经现有 ModelRouter 注册 `query.rewrite`（model-selection §3.7.1），只在 09 §4.1 条件成立时补救。开关放编排配置，模型路由放实际 models.yaml 并从它生成展示表，不新建服务或 SSE 类型。多轮状态更新由票 37 承接。

**Blocked by:** 28（tool_call 与 evidence 事件 + EvidenceDrawer）、30（读图观察 diagnose.vision）、31（预写排障计划表与 seed）

**Status:** done-with-gap（2026-09-13 复核：读图挂接由票 30 完成（串行于检索前，非并行）、取消 / 晚到结果由票 38 + 票 45 巡检覆盖、名额争用由票 45 巡检覆盖；唯一缺口是「人工标注的开关对照样例报告」——需要人工标注样例与真实模型多轮对比，开关保持 false，随票 42 bake-off 补齐）

**Owner:** Claude Code B（2026-09-12 认领；`orchestrator/app/diagnose/`、`config/retrieval.yaml`；graph.py retrieve 节点扩展为 diagnose 流水线；读图（票 30）未做，先走文本路径）

- [x] A1 输入下 plans_ranked 首位为毛发缠绕计划（假 router 单测；真实 DeepSeek + WeKnora：rv_suction_hair_wrap 0.9，引用 X9 Pro 手册 c12 与同型号工单，其后 filter_clog 0.3）
- [x] 输出中不在枚举内的 plan_id 被丢弃并记录（宽松解析后按允许集合过滤，单个越界只丢该假设；无效 evidence_id 剔除、无证据假设丢弃；retrieval_trace 的 synthesize 条记 dropped，日志 event=hypothesis_dropped）
- [x] 并行执行的读图与检索用 LangGraph reducer 合并到不同字段（无覆盖）（**差异**：票 30 把 vision 节点放在 retrieve 之前串行执行（读图观察过 CP-in 后再检索，R4 可省掉检索），未做并行分支；`retrieval_trace` / `image_observations` 的 reducer 仍保留，synthesize 消费 image_observations；test_vision_graph 覆盖）
- [x] 第二次检索在剩余预算 < 3 s 时被跳过并记录（补救判定先要求剩余 ≥ 8 s；改写通过后剩余 < 3 s 记 second_round_skipped；测试用消息时间回拨 20 s 验证）
- [x] 固定样例验证已确认型号 +「不吸了」生成相同 query；去重 / 空白清理不丢失否定、部件和错误码（`app/diagnose/query.py::build_query` 纯函数；样例 `eufy X9 Pro 不吸了`、`eufy X9 Pro 滚刷 不转 报 E12 错误 不吸了`）
- [x] category_only 的 query 不包含候选 SKU，返回证据不含 SKU 专属知识；unknown 不发起检索（query=「扫地机器人 不吸了」，scope.sku=None 由适配器过滤；unknown → build_query 返回空，不发请求）
- [x] 抽取失败时以已确认产品 + 用户原文查询；无文本 / 症状且无图片时追问，不凭空生成故障（原文以型号开头时去重；空内容 → knowledge_status=no_query 不检索、不生成假设，追问由票 24 的 clarify 承担）
- [x] 默认开关关闭，普通文本检索不调用 query.rewrite；每库先查一轮，图片新增信息仍可按既有规则使用唯一补检索名额（`config/retrieval.yaml query_rewrite.enabled=false`；trace 记 rewrite_decision reason=disabled；名额字段 `rewrite_used` 持久化在状态，票 30 的图片补检索复用同一名额）
- [x] retrieval_trace 可核对实际 query / scope / status / hit_ids / scores；internal 抽取与查询全文不流入 message 事件，卡片仍消费原有协议（每库每轮一条含 session/run；测试断言 query 不出现在任何事件 JSON；tool_call.summary 只有「检索知识库 / 命中 n 条来源（已补检索）」）
- [x] 开关开启、非空允许集合且首轮实际请求均 no_match：「它跑完了，地上还是一堆渣」触发一次 rewrite invoke，第二轮找到适用来源后进入允许计划；两轮的 scope / 允许文档集合一致（假 router 返回「扫地机器人 清扫后残留碎屑 清洁效果差」，校验通过，第二轮同 scope 命中后 plans_ranked 进入 hair_wrap；注意票 24 的澄清规则要求该口语句先由 intake 抽出症状，否则会先追问）
- [x] 空集合、unknown、已有 hits、任一库 unavailable、回放或待澄清时，不触发 rewrite；部分库故障不能被汇总为正常无命中后误触发（`should_rewrite` 决策表按库状态与允许集合判定；单测覆盖每一行）
- [x] 空 / 超长 / 格式错误 / 与原查询相同 / 新增型号、错误码、原因或改变否定的改写被弃用；同义表达使用已审核映射；校验失败不另调模型裁判、不写回业务事实（`validate_rewrite`：10 类拒绝原因参数化测试；新中文片段须能分解为原文子串或 retrieval.yaml 已审核同义词；只影响检索 query，不写 symptoms）
- [x] fake clock 验证剩余 < 8 s 跳过补救、invoke ≤ 3 s、补检索整轮 ≤ 3 s；模型 attempts 共用预算，补救失败不延长 deadline、不阻断原降级出口（剩余 < 8 s 跳过与失败回落 standard_flow 已测；rewrite invoke 预算 = min(3 s, 剩余 − 3 s) 由 Router 内部共用；**差异**：「补检索整轮 ≤ 3 s」无节点级硬超时，靠适配器 8 s 客户端超时与 run deadline 兜底；票 45 `rewrite_on_budget_insufficient` 巡检决策表 budget 行）
- [x] 图片新增补检索与改写最多占用一个名额；晚到图片仍过 CP-in、不得再触发第三轮；恢复 checkpoint 不重新 invoke 或重复占用补救名额（名额 `rewrite_used` 持久化在状态，改写被拒也计名额且无第三轮；票 30 读图观察过 CP-in；票 45 `rewrite_on_image_contention`：含图 run 至多两轮、rewrite invoke ≤ 1）
- [x] 取消 / deadline 后的晚到结果不应用、不继续下发卡片；第二轮无结果不递归改写，转票 33 的预写计划或 R5（不递归改写、无证据回落 standard_flow；取消 / deadline 由票 38 的 cancel_event 中断节点并停在上一 checkpoint，晚到工作不落状态；票 45 `late_result_after_cancel` / `rewrite_on_second_round_empty` 巡检）
- [ ] 人工标注的开关对照样例报告含适用证据命中、错误匹配、语义漂移、额外耗时；注册路由 / 配置可校验，未完成启用评估保持 false（路由 `query.rewrite` 已注册两通道并进路由表，`retrieval.yaml` 可校验，开关保持 false；票 45 报告已按开关分别给出 invoke / 轮数 / 额外延迟 / 回退（stub 路由层面）；**缺口**：需要人工标注的口语漏召回样例与真实模型对比才能评估语义漂移，本轮无标注数据，未做；开关保持 false 即为默认安全态）

**设计依据：** 01 F3/F3b；03 §1.4–§1.4.2；09 §3.2、§4.1；08 §8；model-selection §3.7.1

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/diagnose/`（config.py 读 `config/retrieval.yaml`；query.py 规范化；rewrite.py 决策表 + 校验 + query.rewrite 调用；synthesize.py 假设汇总与过滤、无证据 / 模型不可用回落 standard_flow）；graph.py `retrieve` 扩展为流水线（首轮两库 → 可选一次补检索 → synthesize），状态新增 `retrieval_trace` / `image_observations`（reducer）、`plans_ranked`、`retrieval_rounds`、`rewrite_used`、`query`；`app/plans/runtime.py` 进程级计划库；models.yaml 注册 `query.rewrite`（可选任务，缺链不阻止启动）并把 deepseek 加入 diagnose.synthesize 降级位。`tests/test_diagnose.py` 24 项。[~] 为部分完成，留给票 30 / 38 / 42。
