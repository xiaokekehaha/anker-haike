# 赛题解析 vs 当前实现：差距分析与补充清单

日期：2026-09-14。比较材料见 [findings.md](findings.md)。依据为工作树代码与 `docs/planning` 既有文档（分支 `feat/memory-optimization`），是设计/实现对照，没有做线上运行验收，未访问数据库。

## 一句话结论

赛题把靶子从「会答」挪到了「会办」：评的是 **L3 闭环 + 五个难点 + 三项基线**。我们现在是一套工程化程度很高的 **L2 引导系统**（受限排障 + 证据约束 + 安全规则 + 会话记忆），但按前置决策 D2/D3/D16/F13 主动止步于「生成转人工摘要 → END」，**L3 业务办理层是零覆盖**。五个难点里，「幻觉」在排障域内做得最实，「问清」中等偏好但只覆盖扫地机吸力一个故障族，「看图」停在观察层没有故障定位，「分流」和「接稳」最薄。技术框架、业务流程、技术难点三块都要围绕 L3 和五难点补一轮。

## 1. 三阶段定位对照

| 阶段 | 赛题要求 | 我们现状 | 判断 |
| --- | --- | --- | --- |
| L1 问答 | 知识库找答案 | WeKnora 混合检索 + 本地 FAQ 索引 + 范围过滤 + 四态结果；六个高级检索开关（multi_query / faq / rerank / parent_expand / grade / query_rewrite）**默认全关**，评测集 56 条标注 0 条 | 有，且比黑盒 KB 可控——正好对上文档「别套 Bedrock KB」的提示，可作卖点；但开关未启用、评测未闭环 |
| L2 引导 | 多轮追问、收集信息、分步引导 | 14 类意图的语义解释器、product_state 三分 + R7 追问上限、5 条预写计划按 next_on 推进、步骤反馈闭环、事件溯源记忆 V2 | 主干完整，是当前最强部分；范围只有 robot_vacuum × 吸力异常 |
| L3 闭环 | 调后端系统办成事：退款、换货、派单；简单咨询：查物流、查保修、改地址 | `ActionKind` 仅 7 种会话动作（select_product / step_feedback / confirm_receipt / skip_receipt / request_human / new_issue / resume_issue）；退换/保修诉求命中 R6 → 收凭证 → L1–L6 事实核对 → 摘要 → END；`order_verified` 的下一步仍是「转人工办理」 | **零覆盖**。没有业务动作、没有政策判定、没有执行回执、没有案件对象 |

证据：[actions.py](../../../contracts/haike_contracts/actions.py)、[warranty/service.py](../../../orchestrator/app/warranty/service.py)、[graph.py `summarize`](../../../orchestrator/app/sessions/graph.py)、[00_decisions.md](../2026-09-12_smart-service-tech-design/00_decisions.md)。

## 2. 三项基线对照

| 基线 | 当前可测口径 | 差距 |
| --- | --- | --- |
| 独立托管率 70–80% | analytics 的 outcome 分类（resolved / escalated / abandoned / errored…）可推出「未转人工占比」，但没有定义为托管率指标，也没有报表 | 需明确分母（排除澄清中/放弃）、分子（resolved + 自主办理完成），在管理台加指标 |
| 意图识别 ≥90% | `scripts/eval_conversation.py` 对 semantic-gold（15 族 × 5 表达，合成）跑 primary_intent accuracy | 样本是自写的、无真实脱敏工单；意图集里没有 L3 业务意图（查物流/查保修/改地址/退换货/退款） |
| NSS ≥60% | 无。前端没有满意度采集，仅有步骤反馈 solved / not_solved / cannot_do | 需要会话末满意度问卷 + 后台聚合；演示期可用评委打分模拟 |

## 3. 五个难点逐项对照

| 难点 | 赛题口径 | 现状与证据 | 差距 |
| --- | --- | --- | --- |
| ① 看图 | 识别后的信息提取，精准锁定故障位置 | `diagnose.vision` 只输出 `observations`（≤20 字现象）+ `visible_parts`，明确「只是观察不是假设」；安全词进 CP-in；失败则按文字继续；无清晰度/证据充分性字段 | 缺「部件 → 位置 → 现象 → 严重度 → 可读性」的结构化提取；缺图文冲突判定；缺「必要照片缺失暂停并要求补拍」；未验证真实故障图（票 30 用假 router 验收） |
| ② 问清 | 口语、主观描述 → 精准故障类型 | intake 抽 symptoms + 语义解释器 14 意图 + facts/corrections；澄清 R7 两次上限；同义词表 11 组手写、仅吸力域；`query.rewrite` 三家 62–75% 未达标、默认关 | 故障类型归一化只有 5 张计划卡的 keywords 命中；无多品类症状分类体系；澄清问题不是按信息增益选的；口语→规范症状的映射没有数据驱动 |
| ③ 分流 | 一句多诉求；多渠道/国家策略差异 → 路由对的流程 | `secondary_intents` 只在 reduce 里存下来，没有任何消费者；多 issue/多设备已支持；`Dealer.region` 字段存在但 lookup 只按名称精确匹配；`KnowledgeScope` 只有 product_state / category / sku | 多意图不拆分、不排序、不并行；**没有购买地/使用地/平台/渠道维度的政策模型**；没有政策版本与冲突优先级；只有一个品类 |
| ④ 接稳 | 不满 → 暴怒 → 投诉风险递进，分策略接 | 三级情绪（calm / anxious / angry）由规则映射到三种 prompt 层（normal / reassure_first / reassure_and_shorten）+ 安抚句先出；「投诉」是 R3 文本词直接升级 | 只有语气层，没有**策略矩阵**（降速/主动升级/补偿建议/升级到主管）；没有情绪轨迹（连续多轮愤怒）触发；投诉风险等于关键词，不是分级；反讽/emoji 未处理；无接稳效果评测 |
| ⑤ 幻觉 | 按设计的策略和流程执行而非自由发挥 | 排障域最实：hypotheses 限 `Literal[plan_ids]`、evidence_id 必须在范围内否则丢弃；步骤只改写 instruction_src 原文；CP-pre-step 高危动作过滤；`<data>` 包裹 + 注入声明；知识 unavailable 不用常识补；凭证润色禁词表 | 这套约束**只覆盖排障，不覆盖业务办理**：没有政策依据引用、没有承诺一致性（多轮补偿金额）、没有动作授权门（allowed_actions）、没有多模型交叉审核（ModelRouter 首个成功即返回） |

## 4. 技术框架需要补充

现有框架（[06_architecture-final.md](../2026-09-12_smart-service-tech-design/06_architecture-final.md)）四个边界：前端↔编排（契约）、编排↔知识（KnowledgeAdapter）、编排↔模型（ModelRouter）、编排↔规则（三个检查点）。要补第五、第六个边界，并调整两处定位。

### 4.1 新增：业务办理执行层（Action / Tool 层）

- **动作注册表**：`refund.create / replacement.create / rma.dispatch / logistics.query / warranty.query / address.update` 等，每个动作带 schema、前置证据要求、幂等键、回执结构。07 §14「工具定义即 API」有原则没有实例。
- **执行适配器**：赛题不给真实系统，需要**模拟后端**（订单、RMA、物流、退款）作为独立服务或 mock 模块，返回可追溯回执；接口形状按真实系统设计，便于替换。
- **授权门**：动作执行前过「政策判定 + 证据充分 + 用户确认 + 权限」四道；不满足的落人工。复用现有 `prepare_card → await_input → apply_action` 的 interrupt 机制做用户确认卡。
- **回执与失败处理**：外部执行的超时、部分成功、回滚；现有 action_id 幂等只到会话层，不是外部业务幂等。

### 4.2 新增：售后政策规则引擎（与安全规则分离）

- 输入维度：SKU/品类、购买渠道/平台、购买地、使用地、购买日期、凭证状态、故障定性（用户损坏/质量问题/安全）、历史补偿。
- 输出：资格（维修/换货/退款/不支持）、费用承担、允许动作集合、政策条款引用（可展示给用户和评委）、生效版本。
- 与现有规则的关系：`safety_terms.yaml` R1–R8 决定「继续排障还是升级」，新引擎决定「能办什么」；两者都需要规则编号 + 依据记录以满足可解释要求。SOP 规则要有「文本 → 规则」的编译/审核流程，而不是塞进 prompt。

### 4.3 新增：案件（Case）生命周期

会话/run 是分钟级，退换修/物流是天级。需要独立的 case 对象：状态机（open → diagnosing → proposing → awaiting_approval → executing → tracking → closed/reopened）、责任人、待决事项、外部单号、结案条件与客户确认。`done(completed)` 不能当结案。

### 4.4 新增：人工协同工作台（HITL）

现有 `/admin` 是观测台（会话列表、旅程、瓶颈、案例标注），不是客服接单台。需要：接单队列、AI 处置建议 + 备选 + 政策依据 + 回复草稿、人工修改/审批记录、审批后 AI 执行并回写。可先做最小版：一个审批卡 + 一条执行回路。

### 4.5 调整：与 AWS 能力的关系

仓库 `docs/` 与 `config/` 里**没有任何 AWS / Bedrock / Step Functions 的记录**。现状是 DashScope / DeepSeek / Zhipu + Anthropic / Google 直连，编排用 LangGraph，检索用腾讯 WeKnora。需要在方案里明确表态：

- 模型：在 `models.yaml` 增加 `bedrock` provider（Claude / Nova 经 Bedrock），LangChain 有现成集成，成本低；国内通道保留为降级链。
- 编排：说明为什么用 LangGraph 而非 Step Functions（进程内 interrupt、checkpoint、事件流细粒度），或把 Step Functions 定位为**案件级长流程**（跨天的 RMA / 物流跟踪），LangGraph 负责会话级。
- 检索：把「自研 RRF + 可选 rerank + grade + 范围过滤，而不是黑盒 KB」写成响应文档提示的设计点。
- 数据：脱敏数据可能有驻留要求，需确认能否出 AWS。

### 4.6 调整：数据与知识层

- 品类：`products.yaml` 15 个扫地机 SKU + 6 个范围外；计划 5 条、故障卡每 SKU 5 条同样故障。要接**多品类**知识库和工单，目录、故障卡、计划、症状词表都要可扩展，不能手写。
- 真实脱敏工单：现有 `tickets.csv` 是 200 条脚本生成、字段 8 个；真实工单 schema 未知，ingest 只拣固定 metadata。需要工单清洗 → 结构化（症状/根因/处置/结果/渠道/地区）→ 入库的管线，并保留出处。
- 经销商名录：现有 2 条演示记录；真实名录要带 region / 授权状态 / 政策备注，并进入政策引擎。
- 知识发布状态（draft / approved / published / withdrawn）和适用范围元数据（区域、版本）目前没有，[agentic-rag-evaluation](../2026-09-13_agentic-rag-evaluation/evaluation.md) 已提过。
- 多语言：F12 明确「仅中文」；多区域必然多语言，至少中英。

### 4.7 调整：评测框架

现有 bakeoff / kb eval / inspect / replay 测的是模型合规率、hit@5、plan_match、延迟。要增加与基线对齐的三项 KPI 采集，加上五难点各一套小样本评测（图→提取字段准确率、口语→故障类型准确率、多意图拆分准确率、情绪分级准确率、办理越权率 = 0）。样本应尽量来自脱敏工单。

## 5. 业务流程需要补充

当前主链：`understand → route_entry → disambiguate → clarify | vision → retrieve → guide → await_input → feedback → close | escalate → (receipt) → summarize → END`。需要补七段：

1. **简单咨询快路径（30%）**：意图集加 `logistics_query / warranty_query / address_update / order_query`；走「意图 → 取参数（订单号/手机号）→ 调工具 → 回答 + 引用」，不进排障。目前这些会落到 unknown / explain。
2. **售后方案决策**：排障 EXHAUSTED 或用户提退换 → 政策引擎判定 → 生成方案（维修 / 换货 / 退款，含依据与费用）→ 用户确认卡 → 执行 → 回执。取代现在的「R6 → 收凭证 → 摘要 → END」。
3. **多诉求分流**：`secondary_intents` 拆成子任务，按优先级（安全 > 办理 > 排障 > 咨询）排序，逐个处理并告知用户顺序；跨渠道/国家差异在 disambiguate 后补一步「服务上下文确认」（购买地/渠道/平台）。
4. **情绪分级接稳**：把三级扩成「平稳 / 不满 / 暴怒 / 投诉风险」四级 + 轨迹（连续两轮愤怒、重复未解决），每级绑定策略：话术层（已有）、节奏层（减少追问、直接给方案）、动作层（主动升级、提前进入方案决策、补偿建议需审批）。「投诉」不再是关键词直升级。
5. **人工协同回路**：escalate 后不 END，进入 `awaiting_human`；人工在工作台看摘要 + 建议 → 批准/修改 → AI 执行 → 回到用户会话告知结果。
6. **跟踪与结案**：执行后进入 case tracking，外部状态（物流、维修）回写并主动通知；客户确认后结案，未确认或再次求助可重开。
7. **看图流程深化**：`vision` 输出扩为结构化故障定位；判定图片是否足够（清晰度、是否包含必要部件）；不足则发「补拍指引卡」而不是静默按文字继续；图文冲突时先澄清。

## 6. 技术难点需要补充

仓库已记录的难点集中在基础设施（WeKnora v0.8.0 缺陷、厂商 thinking 模式陷阱、智谱 429、评测饱和、延迟/成本、历史记忆幻觉、配置与镜像配对）。面向赛题要按五难点 + L3 重新组织，并补以下内容：

| 方向 | 需要补充的难点描述 | 现有基础 |
| --- | --- | --- |
| 看图 | 从「观察」到「故障定位」的结构化提取（部件、位置、现象、严重度）；多图/铭牌读型号省一轮追问；图片可用性判定与补拍引导；图文矛盾的处理顺序；国内视觉模型在真实故障图上的稳定性（bakeoff 显示 deepseek / qwen-vl 83%，glm-v 77%） | vision 节点、observation_terms 安全过滤、max_images 裁剪 |
| 问清 | 口语/主观/错别字 → 规范症状与故障类型（当前 rewrite 62–75%，词表手写）；多品类症状体系；下一问的选择（信息增益 vs 用户耐心）；已否定事实不复活（已有 corrections）；小语料下检索分数无区分度导致「无知识」判定困难（RRF ≈0.016，5/5 泄漏） | 语义解释器、facts/corrections、R7、同义词表 |
| 分流 | 一句多意图的拆分与优先级；购买地 ≠ 使用地、平台 ≠ 渠道的政策路由；政策版本与冲突优先级；路由不确定时的澄清 vs 猜测 | secondary_intents 字段、多 issue、Dealer.region |
| 接稳 | 情绪分级（不满/暴怒/投诉风险）与策略矩阵；情绪轨迹而非单轮；反讽与 emoji；接稳与效率的平衡（过度道歉拖慢办理）；如何评测「接得稳」 | 三级情绪 + 三层 prompt + 安抚先出 |
| 幻觉（L3 域） | 动作不越权（allowed_actions 白名单 + 授权门）；承诺一致性（多轮补偿口径、金额、时限）；政策引用可追溯到条款版本；执行幂等与回执核对；多模型交叉审核的取舍；检索不到诚实升级（已有） | plan_id / evidence_id 白名单、CP-pre-step、禁词表、四态知识结果 |
| 交付与数据 | 脱敏工单清洗与结构化、多品类目录生成、SOP → 规则编译与审核；模拟后端系统的可信度；AWS 环境接入与数据驻留；现场演示的可复现（replay 已有，需覆盖办理链路） | ingest / snapshot / replay / release 机制 |
| 既有遗留 | 六个检索开关未启用且评测集未标注；单副本假设（多副本协调未建）；告警 sink 未配置、health 误报；前端单包 581 kB；bakeoff 7/10 任务缺合规备链 | 见 [overall-acceptance/report.md](../2026-09-13_overall-acceptance/report.md) |

## 7. 建议优先级

预赛材料 9/27 截止（见 [budget-materials/findings.md](../2026-09-12_budget-materials/findings.md)），最终需现场交互演示。按「能在演示里证明 L3 + 五难点」排序：

- **P0（决定是否算 L3）**：模拟后端 + 1–2 个业务动作（如换货申请、物流查询）+ 授权门 + 用户确认卡 + 回执；政策引擎最小版（1–2 个 SKU × 2 个区域/渠道的质保规则，带条款引用）；情绪四级策略矩阵；vision 结构化故障定位 schema + 补拍卡。
- **P1（补齐难点深度）**：多意图拆分与排序；简单咨询快路径；人工审批回路最小版；case 对象与结案；三项 KPI 报表；五难点小样本评测集（优先用脱敏工单）。
- **P2（方案完整性）**：Bedrock provider 与 AWS 定位说明；多语言；真实工单/名录/SOP 管线规模化；多模型交叉审核；启用并评测六个检索开关。

以上均为待实现设计，本文件不改变任何代码或配置。
