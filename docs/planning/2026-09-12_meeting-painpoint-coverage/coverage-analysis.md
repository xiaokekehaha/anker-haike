# 会议痛点与当前系统架构覆盖分析

日期：2026-09-12；对象：anker-haike 当前工作树，含未提交修改。讨论中的安克内部线上系统不在本仓库，本报告不能据此审计其内部实现。

## 结论

现有底座适合继续建设，支持受约束的诊断、知识检索、可追溯证据、会话恢复和人工输入；目前业务边界是“扫地机排障 → 购买凭证核对 → 转人工摘要”。会议提出的完整目标还包含“客服审阅原文译文 → 选择处置方案 → 审核回复 → 执行业务 → 跟踪结果”，这部分尚未建成。

要区分三个层次：组件可以复用，不等于流程已经接通；流程接通，不等于真实业务效果达标。下文的难度是基于当前代码的工程判断，不是工期承诺。真实政策、接口、权限及样本准备情况会显著影响工作量。

## 1. 当前架构为什么值得保留

- React + TypeScript 展示事件与卡片；FastAPI 提供消息、动作、快照和 SSE；LangGraph 负责显式流程。新增人工等待与审核节点有既有机制可复用。[总体设计](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-12_smart-service-tech-design/02_overall-design.md:3)
- WeKnora 通过 KnowledgeAdapter 提供检索；按产品品类和 SKU 限定知识范围，并区分无命中与不可用，减少引用错误产品知识及服务故障时编造依据的风险。[知识适配器](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:156)
- 预写计划具有版本、适用范围、证据来源和明确的反馈分支；适合受控排障。[计划模型](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/plans/models.py:24)
- 会话动作使用 action_id、会话锁、版本和卡片校验，能够复用到人工确认交互。[动作入口](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/router.py:154)

这些机制尚不能替代客服角色权限、跨系统交易一致性、政策冲突裁决和业务效果验证。

## 2. 覆盖矩阵

| 会议问题 | 当前覆盖 | 补齐难度 | 为什么 / 缺口 |
| --- | --- | --- | --- |
| FAQ、说明书、历史工单分散 | 已有受产品范围约束的知识检索 | 中 | 可继续导入整理后的资料；接入真实内容还需要版本、适用范围、质量核验。实时库存与订单属于另一类业务数据，不能只靠 RAG。证据 E1。 |
| 产品名称歧义、新人不熟悉型号 | 已有产品确认和澄清 | 低至中 | 有目录与交互卡片，但当前支持范围仅扫地机；多产品需要扩充目录、故障计划与验证案例。证据 E2。 |
| 客户描述不清、图片不能用 | 部分覆盖 | 中 | 已有文本澄清与读图；没有图像清晰度/证据充分性字段。读图失败目前按文字继续，没有完整的“必要照片缺失则暂停并要求补拍”机制。证据 E3。 |
| 转人工后重新翻历史 | 部分覆盖 | 低至中（资料速览）；中高（真实工单接入） | 已保存消息并生成产品、问题、观察、步骤、原因摘要；没有外部工单/通话记录导入合并、客服接单和原话定位工作台。证据 E4。 |
| 不信任摘要，希望看原文翻译 | 原文有基础；翻译未覆盖 | 中 | 摘要默认取原话，可选润色限制为原句标点空白整理；来源抽屉展示的是知识片段。缺语言识别、原译文对齐、消息来源引用、翻译复核；设计明确仅中文。证据 E4、E5。 |
| 选择情况一/二/三，生成、修改并批准回复 | 未覆盖人工处理闭环 | 中高 | plans_ranked 是排障计划排序，默认选第一条，不能直接当退款/换货等售后处置选项。没有客服选择、草稿版本、审批与发送动作。证据 E6。 |
| 排障步骤、反馈、判断是否解决 | 最新主流程已接入，待完整验收 | 低至中（当前范围内完善） | 核查期间新增 guide → 步骤卡 → step_feedback；内存 API 冒烟已验证未解决出下一卡、解决后结束。仍缺症状纠正及完整结束体验，回归尚有失败。证据 E7。 |
| 多轮追问、症状纠正，不让客户重复说 | 部分覆盖，未完整实现 | 中 | 保存对话，并有有限澄清历史判断；intake 仍只传本轮文本与少量状态，symptoms 被本轮抽取覆盖；rediagnose 显式拒绝。证据 E8。 |
| 判断重置/清洁、返修、换新及严重程度 | 仅支持有限排障和升级基础 | 高（完整业务定性） | 当前计划描述诊断与操作，规则主要决定升级，缺返修/换新/补偿的资格、费用、授权和可执行条件。情绪标签也不等于识别出“纯情绪投诉”。证据 E6、E9。 |
| 英国购买、德国使用等跨地区政策 | 未覆盖 | 高 | KnowledgeScope 只含产品状态、品类、SKU；没有购买地、服务地、政策生效版本与冲突优先级。经销商虽有 region，但当前核对未据此裁决政策。证据 E1、E10。 |
| 多轮协商补偿金额保持一致 | 未覆盖 | 中高 | 会话动作幂等可防同一动作重复执行，但缺补偿政策、额度/币种、累计补偿记录、方案版本与授权审批。新一轮新动作仍需业务级规则约束。证据 E6、E9。 |
| 查库存、退款、补单、退货标签、仓库发货 | 未覆盖真实业务 | 高 | 当前订单为模拟参考数据且查询结果仍要求转人工；没有对应业务动作、执行器和物流回执状态。需要真实接口、权限、业务幂等、失败恢复和长周期执行跟踪。证据 E6、E10。 |
| 高价设备返修、翻新件、储能线下服务 | 未覆盖 | 高 | 超出当前产品与状态机范围；需要维修单、设备状态、服务商/工程师调度和履约状态。不能通过新增几个产品名称完成。证据 E2、E10。 |
| 发送正确的操作图片/视频 | 未覆盖专门的媒体指导链 | 中 | 已有用户图片输入；知识 bootstrap 关闭多模态分块，计划步骤无媒体字段。需要媒体资源、适用型号/步骤关联与展示校验。证据 E11。 |
| 成功案例提炼，人工审核后入知识库 | 仅有知识导入基础 | 中高 | 有版本化导入，但没有候选知识、审核人、审核状态、发布和驳回的闭环，不能把导入 CLI 等同于反向学习。证据 E11。 |
| 多模型交叉审核降低错误 | 只有路由降级，没有交叉审核 | 中（接入）；高（证明有效） | ModelRouter 首个成功结果直接返回；没有独立审查结果、分歧裁决、升级规则。接多家模型本身不构成验证。证据 E12。 |
| 缩短处理时间、证明准确率与满意度 | 延迟指标已有，业务效果未证明 | 中（埋点）；高（真实效果验证） | 已有首可见/首卡延迟 P50/P95；没有完整客服接单至办结计时、CSAT 与真实案例准确率结果。评测仍在建设中。证据 E13。 |

## 3. 三个容易高估的点

### 有“转人工摘要”不等于已经转接真人

图在 summarize 之后直接 END。前端文案写“已为您转接人工”，但这条代码链没有客服分配、接单确认或外部工单发送实现。因此当前能确认的是“生成交接资料”，不能宣称真实客服已经收到。[结束边](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1450)、[前端文案](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/SummaryCard.tsx:51)

### 有“规则服务”不等于已经覆盖售后政策

现有规则主要为人工请求、安全词、退换诉求标记及排障限额。退款多少、是否换新、跨国政策适用和审批权限属于新增业务规则。[输入规则实现](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/rules/service.py:154)

### 有“checkpoint”和测试通过不等于理解正确、业务完成

checkpoint 保存了状态；如何将正确历史送入模型、怎样保留否定纠正还需要实现。核查期间 guide 和 step_feedback 已接入，verify 判定由 apply_action 内的函数完成，不必是独立图节点。内存 API 已验证基础反馈推进，但成功结束时当前 stage 仍为 verify；完整结束体验及回归尚待收尾。不能以函数存在或若干用例通过代表全部验收通过。

## 4. 建议建设顺序

1. **先稳定原范围闭环。** 验收刚接入的 guide → 步骤卡 → step_feedback → verify，补结束体验、rediagnose 和会话事实合并。用一个连续工单验证“客户纠正症状、重复点击、刷新、未解决升级”行为。
2. **优先实现会议最明确的人工辅助需求。** 用原文和逐条译文、产品、已做步骤、政策依据构成客服速览区；增加可修正的处置选项、回复草稿与人工确认。初期可以用已确认的模拟业务规则，但界面需清晰标明演示边界。
3. **将政策判定与业务执行分开补齐。** 政策负责适用性、金额、权限与决策依据；执行层负责退款/换货/物流等命令、状态与回执。会话持续时间短，返修与物流可能跨天，应有独立案件及执行状态，避免用一次 run 的完成表示结案。
4. **接入真实资料与接口后再扩产品。** 对每个产品维护可审核的排障/处置规则、证据要求和反例；跨地区政策需要业务确认。知识审核与业务指标同步补齐。
5. **用对照数据证明价值。** 记录阅读证据、选方案、修改草稿、实际办理的耗时，统计误判/错误承诺、人工修改率与客户反馈，再判断是否达到目标。会议的“99%”应先定义分母、严重错误类型和样本范围。

技术底座无需因这些需求整体推翻；人工工作台需要新增业务流程，跨国售后与履约执行则需要新增领域能力。真正相对容易的是展示和组织已有信息，最难的是获得可信业务规则、让操作正确落地并证明效果。

## 5. 证据索引

- E1：[KnowledgeScope 字段](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:40)、[范围过滤](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/adapter.py:156)。
- E2：[产品范围配置](/Users/xiaoke.zhou/Documents/workspace/anker-haike/config/products.yaml:5)、[范围外升级](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/clarify.py:185)。
- E3：[视觉输出字段](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/diagnose/vision.py:39)、[失败按文字继续](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:389)。
- E4：[原文摘要生成](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/escalation/summary.py:98)、[保守润色校验](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/escalation/polish.py:30)、[摘要组件](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/SummaryCard.tsx:38)。
- E5：[仅中文、模拟订单的边界](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-12_smart-service-tech-design/01_background-scope-nfr.md:45)、[来源抽屉](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/EvidenceDrawer.tsx:4)。
- E6：[现有动作清单](/Users/xiaoke.zhou/Documents/workspace/anker-haike/contracts/haike_contracts/actions.py:11)、[诊断默认选择第一计划](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1122)、[计划字段](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/plans/models.py:56)。
- E7：[guide 步骤下发](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:1156)、[动作应用分支](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:551)、[反馈判定函数](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/guide/verify.py:41)、[前端卡片渲染](/Users/xiaoke.zhou/Documents/workspace/anker-haike/frontend/src/components/Timeline.tsx:39)。
- E8：[intake 输入与症状覆盖](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/graph.py:197)、[有限历史澄清判断](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/clarify.py:200)、[rediagnose 拒绝](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/router.py:227)。
- E9：[规则检查](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/rules/service.py:154)、[情绪抽取字段](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/intake/extract.py:37)、[会话动作幂等](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/sessions/router.py:193)。
- E10：[凭证订单/渠道模型](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/warranty/service.py:24)、[核实后仍转人工](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/warranty/service.py:55)、[核对逻辑](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/warranty/service.py:71)、[数据与质保决策边界](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-12_smart-service-tech-design/00_decisions.md:5)。
- E11：[知识导入/版本机制](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/ingest.py:1)、[多模态分块关闭](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/knowledge/ingest.py:36)、[步骤字段](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/plans/models.py:24)。
- E12：[模型链首个成功即返回](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/models/router.py:310)。
- E13：[当前延迟指标](/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator/app/observability/metrics.py:14)、[非功能目标](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-12_smart-service-tech-design/01_background-scope-nfr.md:72)、[评测任务](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-09-12_smart-service-tech-design/issues/42-bake-off-model-freeze.md:3)。

## 6. 本次验证与限制

后端：

```bash
cd orchestrator
uv run pytest -q tests/test_catalog.py tests/test_rules.py tests/test_plans.py tests/test_knowledge_adapter.py tests/test_receipt_lookup.py tests/test_sessions_human.py tests/test_sessions_clarify.py tests/test_sessions_idempotency.py tests/test_vision_graph.py tests/test_summary_polish.py tests/test_observability.py -k 'not live and not isolated_schema'
```

首次结果为 123 passed / 2 deselected（7.55s）。随后其他任务接入 guide 与 step_feedback，同组重跑结果为 **118 passed / 5 failed / 2 deselected（8.60s）**，因此不能宣称当前回归全部通过。排除了真实 WeKnora 与独立数据库 schema 两项测试。

失败用例涉及：test_request_human_when_idle_starts_from_entry、test_category_word_without_model_goes_category_only、test_two_different_actions_are_serialized_not_rejected、test_brush_hair_photo_yields_observation_and_continues、test_vision_chain_failure_does_not_break_run。已见错误主要是旧 idle/completed 预期与新增等待步骤卡行为不一致；仍需开发任务核对契约和更新测试，不能把失败全部忽略。

对新主流程额外运行内存 API 冒烟（关闭真实模型与知识服务）：发送“X10 Pro 吸力不足”后出现步骤卡；提交 not_solved 后出现下一步骤；提交 solved 后 _verify.outcome=done、pending_card=None，steps_executed 共 2 条。该路径通过，结束时 stage 仍为 verify。

前端：

```bash
cd frontend
npm test -- src/components/Cards.test.tsx src/components/SummaryCard.receipt.test.tsx src/App.receipt-flow.test.tsx
```

结果：**3 个文件、8 项测试通过，1.54s**。

另用 Python 读取实际编译图、ActionKind、VisionObservation 与 KnowledgeScope，并复查并行更新后的图代码：guide 已接入，反馈在 apply_action 内判定；动作仍无选处置方案/审批/发送；视觉输出无清晰度字段；知识范围无地域字段。

测试主要验证内存状态、假模型/服务与模拟参考数据的行为；没有执行真实退款、仓储或客服派单，也没有测出真实业务准确率、满意度和四分钟一单的达成情况。仓库存在其他任务并行修改，本报告以本次读取的工作树为准。未修改产品代码。
