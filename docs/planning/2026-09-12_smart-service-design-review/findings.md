# 评审发现

## 已确认上下文
- 当前目录以设计文档为主，没有 Git 仓库。
- 最终架构：06_architecture-final.md；另有 00—05 配套设计及 model-selection.md。
- 已有记录确认：前端 Vite + React 19 + TypeScript，后端 Python + FastAPI + LangGraph，模型全部远程并按环节路由。
- 原设计仍待用户评审；早期 findings.md 留有已经更正的 Preact、模型本机部署等历史内容，应以决策与正式文档为准。

## 待核对
- 状态持久化、恢复与业务副作用。
- SSE 与卡片提交协议的一致性。
- 知识检索隔离、版本、置信度及安全规则。
- 多厂商模型的能力契约与失败降级。
- 赛道流程、演示范围和非功能目标。

## 第一轮候选问题（尚待复核）
- 06 最终架构仍有 Ollama；02 部署仍有本地模型；model-selection 的 Embedding / Rerank 仍本机，和 D7 全远程冲突。
- 03 将 LangGraph messages 流直接映射到用户 message，可能混入内部结构化抽取、诊断 JSON，需查官方流式元数据过滤语义。
- 03 actions 没有载荷、幂等键、会话版本定义；05 错误重试直接重新 POST。中断前先发卡片，恢复是否重复需核对框架语义。
- R4 安全规则标注立即升级，但只有 verify 明确调用规则服务；新图片或中途自由文本没有明确重新进入诊断路径。
- 产品未确认两次后默认通用扫地机；同一目录存在吸奶器，降级会强制猜品类。
- 检索只按 category 过滤；工单未限制成功结果，也未明确 SKU 过滤。
- step_count 仅 not_solved 增加，cannot_do 无界；没有稳定 step_id / 步骤状态与每个假设的步骤序列。
- 03 与 05 step_card / escalation_summary 字段层级不一致；evidence_ids 无法对应缺少 ID 的 evidence 事件。
- 04 单模型 20/30 秒超时、重试及 3 家降级，与 8/15 秒单轮目标没有统一截止时间。
- 基于 prompt_hash 的回放缓存被用来验收新 Prompt，命中条件与测试目标冲突。

## 官方资料复核
- LangGraph interrupts 文档明确：恢复会从包含 interrupt 的节点开头重跑；interrupt 之前的副作用必须幂等。因此当前 guide 生成 → 发卡 → interrupt 的顺序需要拆分持久化节点和等待节点，并固定卡片标识。
  来源：https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph messages 流包含图内各处 LLM 调用的 token，invoke 同样可能发出消息事件；官方给出按 invocation tags / langgraph_node 过滤方法。当前直接映射会把内部结构化结果混到聊天区。
  来源：https://docs.langchain.com/oss/python/langgraph/streaming
- WeKnora 官方 knowledge-search 接口列有 knowledge_base_ids / knowledge_ids；返回结果有 chunk id、knowledge_id、score。设计中的任意 filters 字典不能当作底层能力已验证，需固定接口与映射，或先按产品确定允许检索的知识文件集合。
  来源：https://github.com/Tencent/WeKnora/blob/main/docs/api/knowledge-search.md
- 当前官方 hybrid-search 与 knowledge-search 是两个接口；MCP 文档搜索 hybrid_search 没有匹配。此处只列为集成验证项，不据此断言所有版本不支持。

## 静态检查记录
- 本机 python3 未提供 PyYAML，未安装新依赖。
- Ruby Psych 解析模型 YAML 示例报错（首先命中 flow mapping 内的未引号 URL）；此解析器可能有 YAML 版本差异，不能仅凭该结果判定全部 URL 写法错误。继续隔离 lanes 段验证明显的键值分隔问题。

## 最终基线复核
- 审阅期间 00、01、03、model-selection、progress 有同步更新，已重新读取：默认 domestic，接入百炼 / DeepSeek / 智谱 / Claude / Gemini，购买凭证识别纳入 A3 演示。
- 新增确认问题：03 加入 receipt_card / confirm_receipt_fields，但 05 ServerEvent、pendingInput、组件树都没有对应类型；02 escalate 仍摘要完毕即 done，没有等待凭证及确认字段的迁移。
- 新增确认问题：订单号一旦查中就被归为官方渠道，没有核对 order.sku 与当前产品，也未使用订单实际 channel；低置信度字段确认与查询、规则执行的先后顺序未定义。只按渠道给标准质保表述会让流程输出超出已验证事实。
- YAML 的 lanes 段原样解析失败；只在内存中把 `:{` 改成 `: {` 后解析成功。定位到 model-selection 第 172、176、177 行；原文件未修改。
- 最終架构及其他待审章节暂无对应同步更新。

## 交付前再次同步
- 03 已补齐 OCR 后 interrupt、用户确认后查询；05 已补 receipt_card / confirm_receipt 事件及确认交互；00 已增加 D12 / D13。撤回此前“凭证事件缺失”“未定义先确认后查询”的候选判断。
- 仍存在：05 pendingInput.kind 不含 confirm_receipt、步骤卡与摘要两端字段层级不同、02 总体状态机缺凭证完整分支、订单命中未核对产品和实际渠道。
- 报告 R6 / R7 已按最新修订收窄；其他结论复核仍成立。
