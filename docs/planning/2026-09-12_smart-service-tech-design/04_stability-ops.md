# 第四步：稳定性、性能与容量、监控告警、灰度与回滚

面向黑客松演示环境，目标是「现场跑得稳、出问题能兜住、结果能复盘」，不追求生产级。

## 1. 稳定性

| 风险 | 对策 |
| --- | --- |
| 模型 API 超时、限流或拒答 | ModelRouter 是唯一重试层（厂商 SDK max_retries=0）。每个 task 的预算 = min(task 默认超时, run 剩余 − 2 s)；同模型重试 1 次，链上最多 3 家，总耗时不超过预算；整条链失败发 error 并走模块业务降级。run 级 deadline：文本轮 25 s、含图轮 40 s、凭证轮 30 s（08 §8） |
| LLM 输出不符合 Schema | 校验失败重试 1 次并附错误提示；再失败走模块降级路径 |
| WeKnora 不可用 / 无命中 | ToolResult 四态 ok / no_match / unavailable / replay。仅真实 no_match 可在开关开启时尝试一次同范围查询改写，unavailable / 空范围不触发；未补救或补救失败后，有适用预写计划则标注来源并执行，否则 R5。不用 LLM 常识或回放数据补实时依据（09 §4.1） |
| 图片过大或格式异常 | 前端压缩到 1600px 内；后端拒绝 > 5 MB 并提示 |
| 状态机死循环 | 有限计划：plan_cursor 按 next_on 推进；R1 executed ≥ 4、R1b skipped ≥ 3、R1c 合计 ≥ 6、R2 计划耗尽（09 §3.4）。cannot_do 有独立上限 |
| 路由不确定 / 澄清循环 | 必要信息缺失或冲突先澄清，连续两次答复仍不明走 R7；次数跨 run 保留，与排障 counters 分开（09 §1.1） |
| 重复推进 / 重复卡片 | 动作带 action_id + expected_version + card_id，服务端去重与 409；prepare_card 与 interrupt 分节点，card_id 稳定（08 §3–4） |
| 内部输出串入聊天 | 只有 tag=user_visible 的调用进入 message 事件；结构化调用全部 internal（08 §5） |
| 429 / 限流 | 指数退避 1/2/4 s + 抖动，最多 3 次；全局有界队列 50，满则返回可重试 error（07 §13） |
| 备用模型风格不一致 | 简化模式 Prompt 变体 + message.model_tier 标注（07 §6） |
| 演示网络不稳 | 回放模式：REPLAY_CASE_ID 显式指定录制包，绑定 {prompt_ver, models_ver, kb_ver, rules_ver} 清单，不符则启动报 replay_incompatible；未命中返回 unavailable，不借用其他案例（09 §6） |
| 会话丢失 / 断流 / 刷新 | checkpoint 为权威；session_events 事件日志支持 after_seq 续接；前端先读快照再决定恢复；取消结果持久化（08 §6–7） |
| 安全信号晚到 | CP-in 对每条文本、图片观察、动作备注检查；CP-pre-step 在发卡前再检查；R4 优先于排障与凭证（09 §1） |
| 错误产品进入排障 | product_state 三分；category_only 只允许 category_generic 知识；允许集合为空直接 no_match（09 §2） |
| 凭证误判 | 先确认字段再查；订单命中必须核对 order.sku；低置信未修改字段降为 needs_manual_check；只输出已核实事实，不输出资格结论（09 §5） |

## 1.1 缓存与状态外置
见 07 §9、§12。演示阶段实施：L1 prompt 前缀缓存、L4 目录 / 规则 / 计划内存缓存；图片存 session_images 表；回放录制包随镜像打包。L2 检索缓存与多实例外置保留边界不实施（D12）。

## 2. 性能与容量

- 正常目标（测量口径）：首个可见 delta ≤ 2 s（first_visible_ms）；步骤卡就绪 card_ready_ms：文本轮 ≤ 8 s、含图轮 ≤ 15 s。故障最大等待另见 run deadline（08 §8）。5 并发不降级为目标，冻结前需实测，见 §5。
- Token 与调用量：均值 25k token / 会话、8 次调用 / 会话；演示 50 会话/天约 125 万 token；推算见 07 §2。
- 手段：
  - 情绪识别与线索抽取合并为一次 LLM 调用，减少串行。
  - 文本 query 检索与图片理解并行；图片新增信息与可选无命中改写共享一次补检索名额。改写默认关闭，开启时按 08 §8 预留 3 s 模型 + 3 s 检索 + 2 s 收尾，预算不足跳过；不延长 run deadline。
  - 上下文裁剪：仅保留最近 6 轮 + 状态摘要，单轮输入控制在 8k token 内。
  - 流式输出，前端先渲染安抚句。
  - WeKnora top_k 5，Rerank 只对 20 条候选。
- 容量：模拟数据 200 条工单 + 3 份手册，向量量级万以内，单机 pgvector 足够。

## 3. 监控告警

- 追踪：Langfuse 记录每次 LLM 调用的输入、输出、延迟、token、实际命中模型与降级次数（ModelRouter attempts），按 session_id 与 task 串联；可按模型汇总成本。
- 结构化日志：每次状态迁移记录 `{session_id, from, to, rule_id?, latency_ms}`；每次检索记录 query、命中 id 与分数。
- 补救评估：记录改写触发 / 跳过原因、每库状态、前后 query、额外耗时与模型 attempts；按开关状态分别统计适用证据命中、错误命中、人工评估的语义漂移与 card_ready_ms。澄清记录 reason / attempts，不能把「多搜到文本」直接当作正确性提升。
- 健康检查：/health 聚合 llm、weknora、postgres 状态，前端顶部显示组件状态灯。
- 演示前巡检脚本：跑 A1–A3 及故障场景集（重复动作、连续 cannot_do、首句 / 中途 / 图片风险升级、错产品凭证、刷新断流、WeKnora 断开、全模型不可用、回放未命中），输出通过 / 失败与 first_visible_ms、card_ready_ms。
- 告警：演示环境不接告警系统，用巡检脚本 + 健康灯代替；若接入则对「模型连续失败 3 次」「检索为空率 > 50%」告警。
- 复盘指标：案例通过率、平均轮数、首 token 延迟、检索命中率（RAGAS 离线评估）。这些数据用于预赛文档「预期效果」与「已验证结果」的区分。

## 4. 灰度与回滚

- 配置化对象：Prompt 文件、规则表、模型路由表（config/models.yaml，含通道、链、能力矩阵）、检索参数，全部带版本号放 config/ 与 prompts/ 目录。
- 版本锁定：演示前冻结 prompt_ver、models.yaml（含真实模型 ID）、rules_ver、kb_ver、WeKnora 镜像 tag、回放包清单，写入 RELEASE.md。
- 验证顺序：新 Prompt / 模型 → bake-off 金标实测达标（model-selection 3.8）→ 结构化 fixture 跑协议与规则测试 → 重新录制回放包并更新清单。回放只证明展示链路可运行，不用于验收 Prompt 质量（09 §6）。
- 回滚：切回上一版 config 目录并重启编排服务，不涉及数据迁移；WeKnora 知识库变更前导出快照，回滚即重新导入。
- 数据回滚：模拟数据由初始化脚本生成，可随时重置。

## 5. 依赖职责与资源预算（冻结前核实）

| 组件 | 职责 | 默认 Compose | 备注 |
| --- | --- | --- | --- |
| orchestrator | FastAPI + LangGraph、静态前端托管、ModelRouter、规则服务 | 是 | 唯一有业务逻辑的自研容器 |
| postgres (pgvector) | checkpoint、session_events / actions / images、products / plans / dealers / orders_mock；WeKnora 自身表 | 是 | 会话锁用 advisory lock，不依赖 Redis |
| weknora-app | 文档解析、混合检索 | 是 | Embedding / Rerank 配置为远程 API |
| redis | WeKnora 依赖 | 是 | 编排服务不使用；若 WeKnora 版本不需要则移除 |
| langfuse | LLM 追踪 | profile=observability，默认关 | 关闭时 ModelRouter 只写结构化日志 |

- 「30 分钟从零拉起」「5 并发不降级」「无单点」为目标，未实测；冻结前用巡检脚本在演示机实测并把结果记入 findings.md，不达标则调整目标或降并发。
- 单点说明：模型远程 API 与 WeKnora 各自有降级路径；PostgreSQL 是唯一真正单点，演示前做一次快照备份。
