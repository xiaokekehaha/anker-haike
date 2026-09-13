# 智能体式 RAG：一手资料与架构判断

核查日期：2026-09-13。范围：外部官方文档、官方源码、原始论文；本文件不代替项目代码审计和运行实测。下文明确区分“来源事实”与“针对本项目的推断”。

## 推荐判断

**优先做“LangGraph 有界检索流程 + WeKnora 检索底座”，同时把 WeKnora 内置 Agent 纳入对照实验。** 模型可以决定拆哪些子问题、补哪些证据；代码决定检索范围、最大重试、何时追问、何时停止。框架不是 Agentic RAG 的必要条件，但现有系统已使用 LangGraph 时，另引 LlamaIndex/Haystack 的迁移价值尚无证据。此为结合当前技术栈的工程推断，不是厂商基准结论。

对扫地机器人售后，优先验证：型号/版本约束下的故障排查、口语症状转换为检索词、FAQ 与维修说明跨文档拼接、首次召回不足后的定向补查。缺型号时追问、证据冲突时展示差异、找不到可靠依据时转人工，通常比开放式持续搜索更可控。是否提高正确率必须使用本项目问题集验证。

## 1. 简单工作流优先；Agent 用延迟和成本换灵活性

来源：[Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)，2024-12-19 发布，页面已注明部分工具信息随后发生变化；本次仅采用其稳定架构原则。

- 来源事实：区分预定义代码路径的 workflow 与模型动态决定过程/工具的 agent；建议先用最简单方案，只在需要时增加复杂度；Agent 会增加延迟、成本和累积错误风险；框架并非必要。
- 项目推断：不要把“智能体式”理解成多 Agent 团队。售后路径大体明确，单个协调器加少量确定性节点已经能实现查询规划、证据判断、有限纠错。仅复杂请求进入慢路径。

## 2. LangGraph 官方 Agentic RAG 是可直接借鉴的流程骨架

来源：[LangGraph — Build a custom RAG agent](https://docs.langchain.com/oss/python/langgraph/agentic-rag)。这是当前文档，不表示项目锁定版本具有相同 API。

- 来源事实：示例按“决定是否检索 → 检索工具 → 文档相关性判定 → 生成答案或改写问题并重检索”构图，使用结构化输出进行相关性判断。
- 项目推断：适合在既有图上增加 planner、evidence judge、bounded retry。不能照搬示例的 yes/no 相关性判断充当完整证据检查：本项目还需型号一致性、版本有效性、步骤完整性、引用可回溯和知识冲突检查。
- 实现边界：建议最多 2 轮检索（首次 + 一次补查）、每轮最多 2–3 个子查询作为实验起点；这些是待调参数，不是官方推荐数值或性能承诺。相同查询不重复执行，无新增证据即终止；不要只靠 LangGraph 递归上限。

## 3. WeKnora v0.8.0 已经提供内置 Agent，不能归为新主分支能力

本次通过 GitHub tree API 核实：`v0.8.0` 指向 `1edcd54b43606d9079bb36650efe3f68707a79ea`。后续复现应固定实际部署镜像 digest 与源码 SHA，而不只记录 tag。

核查入口：[v0.8.0 Agent 官方文档](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/03-features/07-agent.md)、[AgentConfig](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/agent.go)、[knowledge_search](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/agent/tools/knowledge_search.go)、[Agent API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/agent.md)。

已确认的版本能力：

| 能力 | v0.8.0 证据 | 对本项目的意义 |
| --- | --- | --- |
| quick-answer / smart-reasoning | 官方文档区分快速 RAG 与多轮 ReAct | 内置 Agent 可作为低改造成本的候选 |
| 多查询语义检索、关键词检索、分块阅读、文档元数据、图谱工具 | `knowledge_search`、`grep_chunks`、`list_knowledge_chunks`、`get_document_info`、`query_knowledge_graph` | 已覆盖常见“先搜索、再补读”原语 |
| 工具和知识范围约束 | `AllowedTools`、`KnowledgeBases`、`KnowledgeIDs` | 应创建专用售后 Agent，显式缩小工具与知识范围 |
| 循环/输出配置 | `MaxIterations`、`MaxCompletionTokens`、`MaxToolOutputChars`、`ParallelToolCalls` | 有控制入口，但不能据此假设已符合在线 SLA |
| 引用与步骤记录 | `KnowledgeRefs`、`AgentStep`、`TurnUsage` | 可尝试转接现有前端/日志；端到端正确性仍需验证 |

特别需要按源码而非页面文字处理的边界：

- [builtin_agents.yaml](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/config/builtin_agents.yaml) 的智能推理 Agent 配置为 50 轮；[custom_agent.go](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/types/custom_agent.go) 自定义 Agent 未填时为 10 轮。这些默认值不宜直接用于在线售后。
- [engine.go](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/agent/engine.go) 的 `withinIterationBudget` 支持负数轮数表示无限制。应显式设置正数。
- [const.go](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/agent/const.go) 明确 `LLMCallTimeout` 控制流静默超时，默认 120 秒；它不是整次请求总耗时限制。源码另提及 provider transport 的 `WEKNORA_LLM_STREAM_TIMEOUT_SECONDS`。部署侧仍需核查真正的端到端 deadline、取消传播和重试时间。
- 同 tag 的 Agent 说明文档仍把上述超时描述成单次调用超时，且部分轮数描述未覆盖负数分支，说明文档和实现存在漂移。正式接入必须以部署源码/行为为准。

项目推断：可做独立路线 B，通过内置 Agent 接口获得最终答案并映射事件与引用；路线 A 则由 LangGraph 管控流程，只调用检索/读取能力。**避免外层 LangGraph 反复调用一个内部会持续规划的 WeKnora Agent**，否则两层循环会使预算、追问和来源追踪难以归属。

## 4. 当前主分支与 v0.8.0 的差异必须单独看待

本次核查的主分支 SHA 为 `fd7fa6a7d407c3fbc6dfb31ea05d9a361373dcdf`，相对 v0.8.0 领先 85 个提交。

来源：[固定 SHA 的比较页](https://github.com/Tencent/WeKnora/compare/1edcd54b43606d9079bb36650efe3f68707a79ea...fd7fa6a7d407c3fbc6dfb31ea05d9a361373dcdf)、[GitHub 比较 API](https://api.github.com/repos/Tencent/WeKnora/compare/1edcd54b43606d9079bb36650efe3f68707a79ea...fd7fa6a7d407c3fbc6dfb31ea05d9a361373dcdf)。

来源事实：提交记录包含 MCP 工具按需发现/调用、工具目录持久化、浏览器控制、运行中追加用户消息、网页检索/读取改进，以及 OCR 图谱抽取、MCP 答案引用等修复。该部分仅核对提交记录，未对全部实现作安全或回归审计。

项目推断：不能用 main 的宣传页替部署版本背书，也不应为本轮 RAG PoC 顺带迁移全部这些能力。若某个已知缺陷影响证据正确性，应针对确切修复评估升级/回补，而非仅因 Agent 功能更丰富就升级。

## 5. LlamaIndex：检索组件与 Agent 可以组合，但换框架不会自动提高答案质量

来源：[LlamaIndex — Building an agent](https://developers.llamaindex.ai/python/framework/understanding/agent/)。

- 来源事实：工具可为普通函数或完整 query engine；提供 `FunctionAgent`，可自定义 workflow，也有多 Agent 的 `AgentWorkflow`。
- 项目推断：适合检索索引/文档工具生态以 LlamaIndex 为中心的新项目；当前 WeKnora 承担知识底座、LangGraph 已承担编排时，换框架会新增适配、状态、追踪和运维工作。本次没有证据证明迁移能优于补齐现有系统。

## 6. Haystack：组件化管道与循环 Agent 是可行替代

来源：[Haystack — Agent](https://docs.haystack.deepset.ai/docs/agent)，本次页面显示文档版本 3.1。

- 来源事实：Agent 可以动态调用工具、维护 schema 状态，并用 `exit_conditions` / `max_agent_steps` 停止；返回步骤数、Token 用量、工具调用计数、退出原因等元数据；默认最大步骤为 100。
- 项目推断：适合团队希望把检索组件和数据管道统一到 Haystack 的场景；就本项目而言列为备选即可。任何框架默认上限都需要针对售后时延调整，默认有上限并不等于业务可接受。

## 7. GraphRAG：全库归纳和关系探索更匹配，单型号故障问答应先证明必要性

来源：[Microsoft GraphRAG — Query overview](https://microsoft.github.io/graphrag/query/overview/)、[原始论文 From Local to Global](https://arxiv.org/abs/2404.16130)。

- 来源事实：Local Search 结合抽取出的实体关系与原文分块；Global Search 通过社区报告执行 map-reduce，面向理解整个数据集的问题，官方明确其资源开销较高；DRIFT 增加社区信息引导跟进检索。
- 项目推断：更适合“不同机型哪些故障有共性”“某部件影响哪些症状”这类跨实体分析；对“某型号某错误码怎么处理”，型号/错误码过滤、混合检索、原文邻近片段往往是更直接的第一轮候选，但是否更优仍需实验。
- 概念边界：WeKnora 提供 `query_knowledge_graph` 不等于已部署微软 GraphRAG 的社区索引/全局搜索，两者不能互相替代地作能力承诺。确定性故障步骤/部件兼容关系也可由结构化表或显式业务图表达，无需预设一定采用 LLM 全库抽图。

## 8. Self-RAG 论文支持“按需检索与反思”的方向，不支持零样本照搬收益

来源：[Self-RAG 原始论文](https://arxiv.org/abs/2310.11511)。

- 来源事实：论文方法训练模型使用 reflection tokens 决定检索与评价生成，在其数据和任务上报告改进。
- 项目推断：可以借鉴“需要检索吗、证据支持吗、是否要继续”这些控制问题，但给现有商业模型追加一个 judge prompt 并不是该论文方法的严格复现。不能套用论文数字预测本项目提升。

## 9. 证据评估需要同时覆盖检索、答案、业务适用性

来源：[Ragas — Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)。

- 来源事实：Faithfulness 检查答案各项主张是否可由检索上下文支持，得分为被支持主张数 / 总主张数。
- 项目推断：该指标适合发现无依据生成，但忠实复述过期或错误型号文档仍可能得高分。因此至少增加：正确型号命中、关键步骤完整、引用确实存在且支持对应主张、冲突时是否正确处理、无答案时是否追问/拒答；并以专家人工样本校准 LLM judge。回答正确性不能只看模型自评。

## 可行性验证建议（工程方案，未实测）

1. 用同一批问题、同一文档快照、相同模型和检索参数对照：A0 当前链路；A1 修复/优化的一次检索；A2 有界 Agentic RAG；B WeKnora 内置 Agent。A1 必须保留，防止把基础检索修复收益误归因给 Agent。
2. 样本分层：单事实、缺型号、口语症状、跨文档、多轮追问、冲突/旧版本、无答案、带错误用户假设。复杂样本单独报告，不能让简单 FAQ 的占比掩盖差异。
3. 分别记录答案质量、引用支持、正确追问/转人工、首字/完整回答 P50/P95、模型调用数、检索轮数、输入/输出 Token、超时率。流式输出更早出现不等于最终答案更快。
4. 成本用实测调用账单/Token 计算；时延按关键路径累计。一次额外 planner/judge/rewrite 都可能新增模型调用；同轮独立子查询可并发，但依赖前轮结果的纠错无法全部并行。
5. 上线条件由业务设定：复杂问题收益是否稳定、简单问题是否退化、P95 是否达标、每解决一个问题的成本是否可接受。不要预先承诺“准确率提升 20%”或固定响应秒数。

## 尚未确定

- 实际运行的 WeKnora 镜像 digest 是否与上述 v0.8.0 源码一致；现有 API 封装具体用了哪些检索/Agent 能力。
- 当前错误主要来自知识缺失/切块/型号隔离，还是缺乏查询规划；前者无法靠多轮思考补齐。
- 当前模型的函数调用、结构化 JSON、中文故障词改写质量，以及线上 P95/并发/预算。
- 文档型号、地区、固件版本、发布日期元数据的覆盖率与可信度；是否存在明确的权威来源和冲突裁决规则。
- 内置 Agent SSE/引用到现有客户端的兼容性、超时后取消传播、每条工具的实际权限过滤与故障降级行为。
- 图谱能否由结构化故障/部件数据直接构建，是否确实有足量跨实体问题支撑额外成本。
