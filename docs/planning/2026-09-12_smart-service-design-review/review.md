# 智能服务最终设计评审

日期：2026-09-12。范围：当前 00—06 技术设计、模型路由、技术调研，以及赛道需求。评审已纳入本轮同步更新的「默认国内通道、多厂商接入、购买凭证识别进入 A3」。文件哈希见 [baseline.json](baseline.json)。

**结论：现有技术栈可以继续推进，开工前应先补齐流程、恢复和数据契约。** 主要风险集中在错误产品进入排障、重复恢复、内部输出串入聊天，以及新增凭证流程尚未闭环。建议先处理下列 P1，再补齐 P2。这里的 P1 指应在对应功能开发、联调前解决；P2 指应在演示冻结前补齐。

本次是设计评审。没有应用实现可供运行，结论来自跨文档比对、状态路径推演、官方框架语义核查，以及 YAML 示例的局部解析。未访问数据库，也未修改原设计。

## P1：影响流程正确性与联调

### R1．把“立即升级”规则落实到每轮输入和发步骤之前

**证据：** [安全规则 R4](../2026-09-12_smart-service-tech-design/03_detailed-design.md:53) 要求立即升级；但明确调用规则服务的位置在 [verify](../2026-09-12_smart-service-tech-design/03_detailed-design.md:42)，[主流程](../2026-09-12_smart-service-tech-design/02_overall-design.md:47) 会先经过 diagnose、guide。intake 只明确将 wants_human 提前分流。

**触发与影响：** 用户首句或补充图片中出现冒烟、鼓包等迹象，按目前写明的主流程，仍可能先生成一条排障操作，再在反馈后触发 R4。等待步骤反馈时，前端还可能禁用自由输入，用户难以及时补充新危险信号。

**建议：** 每轮文本、图片观察和卡片动作进入后，先执行统一规则检查；发出每条操作前再次检查。R4 优先于普通排障和凭证收集。明确安全升级可以直接生成摘要，购买凭证稍后补充；请求人工始终可用。新增症状、照片和用户纠正应有明确的重新诊断入口。

**验收：** 首句有风险、排障中补充风险、图片发现风险三种情况，均不产生后续普通步骤卡。

### R2．未确认品类时不能降级成“通用扫地机”，检索须核对适用型号

**证据：** [产品消歧降级](../2026-09-12_smart-service-tech-design/03_detailed-design.md:23) 将两次未选择的用户送入通用扫地机诊断；而 [需求范围](../2026-09-12_smart-service-tech-design/01_background-scope-nfr.md:25) 明确同名产品可能是吸奶器。[检索流程](../2026-09-12_smart-service-tech-design/03_detailed-design.md:30) 只按 category 过滤，虽然手册已经有 sku_list。

**触发与影响：** 用户未完成消歧就可能收到错误品类操作；已确认扫地机型号后，也可能检索到另一型号的拆装、按键或配件说明。将型号拼进 query 不能保证检索结果适用。

**建议：** 区分“品类已确认、型号未知”和“品类仍未知”。只有前者允许使用标记为该品类通用的知识；后者继续简短追问或升级。进入 guide 前校验 SKU / 明确兼容范围。历史工单保留处理结果，失败步骤作为反证，不能直接改写成推荐动作。

**集成核实：** 任意 `filters: dict` 尚未映射到 WeKnora 的实际接口。可在锁定版本后，将产品适用范围映射到 `knowledge_ids` 或标签；空的允许集合应返回无结果，不能省略过滤后退成整库搜索。[WeKnora 官方混合检索参数](https://github.com/Tencent/WeKnora/blob/main/docs/api/knowledge-base.md)

**验收：** 未选品类不进入扫地机操作；同品类不同 SKU 的专用操作不会串用；选中本期不支持的吸奶器时明确转入范围外处理。

### R3．将排障步骤建模为有限计划，补齐 cannot_do 的退出条件

**证据：** [verify](../2026-09-12_smart-service-tech-design/03_detailed-design.md:42) 仅在 not_solved 时增加 step_count、下调 confidence；cannot_do 只跳过并记录。[R1 / R2](../2026-09-12_smart-service-tech-design/03_detailed-design.md:50) 分别依赖步数和置信度。[硬上限 6](../2026-09-12_smart-service-tech-design/04_stability-ops.md:13) 仍使用相同计数。

**触发与影响：** 连续点击“无法操作”不会触发两个上限，尚未定义的“下一步”可能持续生成。现有状态也没有稳定的 step_id、当前计划位置和剩余步骤，无法保证不会重复操作。

**建议：** 用少量预写排障计划覆盖本期故障，至少定义 `plan_id / version / step_id / status / next_on_feedback`。LLM 改写已选步骤；规则决定下一步。保留实际执行次数，另设推进次数或跳过次数上限；完成、失败、跳过、耗尽均有出口。confidence 可用于排序，不宜单独代表“步骤已经耗尽”。

**验收：** 连续 cannot_do 在有界轮数内升级；已跳过步骤不重复；两条不同操作共享同一故障假设时可以按计划推进。

### R4．中断恢复需要持久化卡片、动作幂等与权威快照

**证据：** [时序图](../2026-09-12_smart-service-tech-design/06_architecture-final.md:96) 为生成步骤 → 发卡 → interrupt；[错误重试](../2026-09-12_smart-service-tech-design/05_frontend-design.md:64) 是重新 POST 同一输入。[接口](../2026-09-12_smart-service-tech-design/03_detailed-design.md:75) 未定义动作幂等键、卡片身份或版本检查。[刷新恢复](../2026-09-12_smart-service-tech-design/05_frontend-design.md:65) 需要 timeline 和 interrupt，但后端状态表尚未定义这份完整视图的持久化来源。

**框架语义：** LangGraph 恢复会从包含 interrupt 的节点开头重跑，之前的代码会再次执行；因此副作用需要幂等。[LangGraph 官方中断说明](https://docs.langchain.com/oss/python/langgraph/interrupts)

**触发与影响：** 用户提交反馈时可能重新生成一条不同的步骤卡，再把旧反馈应用到它上面。后端已接收动作但响应断流时，重新提交又可能重复推进；刷新也不能仅凭 stage 判断旧 run 是否仍在执行。

**建议：** 拆成准备卡片并提交状态、等待输入、验证动作三个阶段。持久化 pending card / interrupt / 已确认 timeline；统一使用 checkpoint 作为业务状态来源，sessions 中的重复 state 必须明确是可重建投影。动作包含 `action_id、interrupt_id、card_id、expected_version`，服务端去重并校验当前待办；同会话串行执行。快照返回 `active_run、pending_input、version`。断流后先读快照，再决定恢复；取消结果持久化供 GET 读取。

**验收：** 卡片确认、同动作重复提交、反馈已提交后断网、服务重启、过期卡片提交，均不重复推进且视图能恢复。

### R5．只把明确面向用户的模型输出送入聊天流

**证据：** [后端流式映射](../2026-09-12_smart-service-tech-design/03_detailed-design.md:139) 直接写明 `messages → message 事件`；intake、视觉观察、假设汇总等多个节点都会调用结构化输出模型。

**框架语义：** LangGraph messages 流可以包含图内各处 LLM 调用的 token，使用 invoke 也可能产生事件；官方支持按调用 tags 或节点元数据过滤。[LangGraph 官方流式说明](https://docs.langchain.com/oss/python/langgraph/streaming)

**触发与影响：** 用户可能先看到情绪分类 JSON、未校验的故障假设或失败重试片段，随后又看到正常答复。给 ModelRouter 设置 stream=false 并没有在设计上定义这条展示隔离规则。

**建议：** 只有明确标记为用户可见的 reply 调用允许生成 message.delta；内部结构化输出校验通过后才进入业务卡片或状态。消息携带稳定 message_id。若用户已看到部分文本，降级不得直接把另一模型从头输出拼在后面，应明确结束、替换或重新开始该消息。

**验收：** 结构化模型校验失败并重试时，聊天中不出现任何内部 JSON；流式主模型中断后不出现两段答案拼接。

### R6．前后端事件结构和凭证恢复状态仍不一致

**证据：** 最新修订已在 [前端 ServerEvent](../2026-09-12_smart-service-tech-design/05_frontend-design.md:45) 增加 receipt_card / confirm_receipt，并在后端明确“先确认字段再查询”，这两项不再作为缺失问题。但 [pendingInput.kind](../2026-09-12_smart-service-tech-design/05_frontend-design.md:95) 仍不接受 confirm_receipt；[总体状态机](../2026-09-12_smart-service-tech-design/02_overall-design.md:39) 仍写成摘要完成即 done。后端 [step_card](../2026-09-12_smart-service-tech-design/03_detailed-design.md:88) 是平铺字段，前端要求 `{step: ...}`；escalation_summary 也分别是 `{fields...}` 与 `{summary: ...}`。

**触发与影响：** 按两份文档分别实现，步骤卡与摘要会因字段层级不同而校验失败；凭证事件虽可解析，却无法直接保存为当前定义的 pendingInput，刷新恢复也没有完整状态依据。等待上传、识别失败、跳过凭证与最终摘要的迁移仍需写入总体状态机。

**建议：** 在 escalate 内完整定义 `collect_receipt → extract → confirm_fields → lookup_channel → summarize`，允许无凭证、看不清和跳过时生成明确的待人工摘要。上传标记图片用途，避免把购买凭证当故障图。统一事件、动作和快照 Schema；让事件和 pendingInput 复用同一个等待类型，并确定卡片与摘要唯一字段层级。

同时补齐引用链：guide 输出和 step_card 带 evidence_ids，evidence.items 带稳定 ID 与文档版本；目前 [Prompt 要求引用 ID](../2026-09-12_smart-service-tech-design/03_detailed-design.md:131)，但步骤载荷和来源载荷无法建立该关系。Schema 应在构建或检查阶段生成、校验，不能仅依赖服务启动时导出后人工同步。

**验收：** A3 实际走完上传 → 修改一个 OCR 字段 → 确认 → 查询 → 摘要；前后端消费同一套 fixture，全部事件均通过校验；每条步骤引用都能定位到确切来源。

### R7．订单命中不能直接等同于当前产品的官方购买凭证

**证据：** [warranty 第 2 步](../2026-09-12_smart-service-tech-design/03_detailed-design.md:63) 规定订单号命中即返回官方渠道；但 [orders_mock](../2026-09-12_smart-service-tech-design/03_detailed-design.md:119) 已包含 sku、channel、purchase_date，没有规定与当前产品核对。最新修订已明确先确认 OCR 字段再查询，但用户确认不能替代订单归属产品和渠道校验。

**触发与影响：** OCR 误读成另一个有效订单号，或用户上传另一台设备的凭证，会得到当前设备的路径提示；经销商订单也可能被改成官方订单。即使没有真实订单系统，这也会让演示的业务判断不可信。

**建议：** 保留先确认再查询的顺序；命中后核对 SKU / 当前产品、保留订单实际 channel 与日期，并对冲突返回明确状态。识别结果保留字段级置信信息和用户修订值。当前范围只做渠道及资料核实，就输出这部分已确认事实和下一步；完整质保资格仍待规则或人工核实，不从授权渠道一项推出资格。

**验收：** 错产品订单、经销商订单、OCR 低置信度且恰好命中另一个订单、资料不全四类情况，不会直接给出当前产品已确认可保的结果。

## P2：演示冻结前应补齐

### R8．统一知识故障、无命中与演示回放的处理方式

**证据：** [详细设计](../2026-09-12_smart-service-tech-design/03_detailed-design.md:32) 在 WeKnora 故障时让 LLM 根据常识生成假设；[稳定性设计](../2026-09-12_smart-service-tech-design/04_stability-ops.md:11) 则切 MockAdapter；[状态机](../2026-09-12_smart-service-tech-design/02_overall-design.md:36) 又规定空检索转升级。

**影响：** 实现者无法确定真实故障应走哪条路径；常识假设 confidence=0.5 仍高于 R2 的 0.3，可能继续生成没有可核查依据的步骤，违背 guide 的来源约束。将模拟命中标成“未命中知识库”也不能准确说明结果来源。

**建议：** 明确 `ok / no_match / unavailable / replay` 四种状态。实时检索不可用时，只能使用适用产品且已审核的固定步骤，否则升级；Mock 仅在显式回放中使用，缓存未命中不得借用其他案例。模型不可用时，升级摘要仍可由状态字段直接渲染，润色失败不应阻断交接。

**验收：** 断开 WeKnora、空结果、全模型不可用、回放未命中，分别进入规定路径且有准确来源标记。

### R9．给整轮设置截止时间，避免多层重试耗尽演示时间

**证据：** [降级规则](../2026-09-12_smart-service-tech-design/04_stability-ops.md:9) 允许每家两次、最多三家，每次文本 20 秒 / 图片 30 秒；[交互目标](../2026-09-12_smart-service-tech-design/04_stability-ops.md:19) 是文本 8 秒 / 图片 15 秒；[前端](../2026-09-12_smart-service-tech-design/05_frontend-design.md:128) 30 秒无事件就中断。

**影响：** 若每次都等到超时，单个 task 就可耗时 120 / 180 秒，尚未计算退避与多个串行 task。前端可能在降级完成前断开。现有设计没有区分正常延迟目标和故障时最大等待。

**建议：** 分别定义正常请求的测量口径、故障下整轮 deadline、各 task 剩余预算，以及唯一重试责任层，避免 SDK、Router、节点叠加重试。心跳只维持连接，不延长 deadline。视觉观察进入 query 的流程本来有依赖，不能同时宣称直接并行；可先按文本检索，观察有新增信息时再补检索。

**验收：** 人为注入超时和 429 后，整个 run 在明确上限内结束或降级；文本首响应和步骤就绪时间分别记录。

### R10．最终架构需要同步全远程部署与实际路由配置

**证据：** [D7](../2026-09-12_smart-service-tech-design/00_decisions.md:14) 已确定模型全远程；[最终架构图](../2026-09-12_smart-service-tech-design/06_architecture-final.md:61) 仍使用 LLM Client、Ollama 主备路径，[部署清单](../2026-09-12_smart-service-tech-design/06_architecture-final.md:78) 仍包含 Ollama。[模型文档](../2026-09-12_smart-service-tech-design/model-selection.md:57) 还推荐容器内 Embedding / Rerank。

**影响：** “最终”文档仍会引导实现者部署已取消的本机推理。最新默认路由表与 YAML 示例也不一致，例如 diagnose.vision 的示例只有 qwen-vl，默认路由表有 GLM 和 Claude 降级位。

**建议：** 最终图明确 ModelRouter，以及独立的远程 Embedding / Rerank 接入；同步已确认的默认通道和凭证分支。将唯一可执行 models.yaml 作为路由表来源，固定真实 model ID、provider、能力和超时，再生成展示表。多厂商接入范围保持现有决定，但配置应检查 task 覆盖与链上别名是否存在。

**已复核的小问题：** [YAML 示例](../2026-09-12_smart-service-tech-design/model-selection.md:172) 的三处 `task:{...}` 缺冒号后空格；lanes 段原样解析失败，仅在内存补空格后通过。原文件未改。这是局部语法检查，不代表完整配置或厂商接入已验证。

### R11．把演示回放与新 Prompt 验证分开

**证据：** [回放键](../2026-09-12_smart-service-tech-design/03_detailed-design.md:111) 包含 prompt_hash；但 [发布检查](../2026-09-12_smart-service-tech-design/04_stability-ops.md:41) 要求新 Prompt 先在回放模式跑通。

**影响：** 修改 Prompt 会改变缓存键，旧录制结果无法命中；若绕过键复用旧结果，又没有验证新 Prompt 的真实输出。三条固定录制可证明展示链路可运行，不能证明新模型或新 Prompt 的质量。

**建议：** 演示回放绑定 case_id 与完整版本清单，严格使用冻结输入和结果；规则及协议检查使用明确的结构化 fixture；新 Prompt / 模型用金标输入实际调用并评价，验证后再录制。缓存键或记录应覆盖输入与图片摘要、输出 Schema、Prompt、模型、知识版本，不能只靠不明确的 prompt_hash。

**验收：** 新 Prompt 在旧回放集上明确报告不兼容；实际评测通过后生成新录制；质量报表明确哪些数值来自实时评测。

## 可进一步简化的地方

- **让规则模块管理有限排障计划。** 本期只覆盖少量故障，预写步骤与分支比逐轮让模型临时组织操作更容易验证，也能减少 LLM 调用。保留视觉观察、口语理解和步骤改写作为 AI 价值。
- **保留 ModelRouter，但让流式契约明确。** 当前 `invoke(..., stream=True) -> ModelResult` 没有描述如何消费增量文本。可定义结构化调用返回结果、文本调用返回异步事件迭代器，厂商格式转换与重试仍封装在模块内部。
- **单独做一份会话执行契约。** 集中定义 run、interrupt、card、action、version、快照和取消语义，避免这些规则散落在前端、后端、模型与运维文档中。
- **在冻结前核实依赖与资源预算。** 将 PostgreSQL 会话缓存、Redis、追踪和知识解析的职责写清；只有实际使用的能力才放进默认 Compose。当前没有部署文件或实测结果，不能据此承诺 30 分钟从零启动、5 并发和“无单点”。

## 推荐修改顺序

1. 先冻结事件 / 动作 / 快照契约，接通凭证卡片，并明确幂等恢复。
2. 补每轮规则检查、产品适用性检查和有限排障计划。
3. 完成凭证确认、订单关联、渠道判断与摘要顺序。
4. 统一降级、deadline、全远程路由和最终架构图。
5. 在 A1—A3 外加入重复动作、连续无法操作、风险升级、错产品凭证、刷新断流和依赖故障场景，再做真实模型评测与回放录制。
