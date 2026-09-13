# 设计输入与发现

## 开发交接审阅（2026-09-13）

以下源码差异是审阅开始时的基线观察。审阅期间另一开发任务已推进 CM-02 并改动源码；本节不作为最新实施完成度，开发接续时以实际代码和测试重新核对。

- README 的“业务实现未开始”与 task_plan 中 CM-01 in_progress 不一致；本轮需统一描述为“实施已启动，完成度以实施记录和源码为准”。
- 数据协议已有接收账本和 checkpoint/effect 协调方向，但还需明确 effect ID、流式事件去重、版本含义、取消/崩溃后的可恢复阶段，避免实现时各模块自行定义。
- 本轮仅补齐设计，不把相邻任务文档中的授权/完成声明视作已验证的实现，也不执行历史清理。
- 已核对源码：runner.version_of() 目前取 checkpoint step+1；如果 V2 用 checkpoint 标记 effect delivered，会引发纯交付重试也改变业务版本。设计改为显式发布版本，与 checkpoint_id、seq 分离。
- RunEmitter.emit() 目前所有事件都过公开 ServerEvent 校验；新增内部 state_committed 需要单独内部事件类型与公开过滤，不能直接塞入现有 parse_event。
- RunManager.reconcile_orphans() 目前无条件写 server_restarted/done(error)；V2 必须按“业务是否提交、输出是否持久化”分阶段恢复，不能照搬旧收尾。
- 当前 reply() 从跨轮累计 evidence 的插入顺序取片段，reply_messages() 再取前六条。V2 必须按本轮/当前 issue 的有效 ID 选证据，否则补了对话历史仍可能使用旧产品依据。
- 当前 ModelRouter.invoke()/stream() 在内部重试主备，外部 ContextBuilder 看不到实际切换时机；预算方案需要覆盖 Router 内部每次实际模型调用，不能只写“切备用时重算”。
- 当前 Composer/useSession.send() 在 select_product/confirm_receipt pending 时阻止普通文本；只改后端无法满足 A09/A10，CM-07 要同步放开。
- settings.py 当前没有会话 timezone 配置；Asia/Shanghai 是 V2 拟新增默认值，不能描述成现有后端配置。recentSessions.ts 的实际 localStorage 键为 haike.recent_sessions。

### 本次补齐的开发决策

- 新增 developer-handoff.md：明确原子接收、候选状态/单次业务提交/发布、终态重放、图片去重、公开/私有事件、快照水位和前端恢复。
- 修订公开 version 为已发布业务版本；风险实体统一顶层存储；切换问题挂起卡片，返回时新 token；session_inputs 替换 session_actions，避免双账本。
- 上下文实际接入各任务；知识在图中传引用、模型调用时解析必要短原文；旧产品/累计插入顺序不得控制本轮证据。主备预算检查覆盖 Router 的实际调用点。
- 明确混合意图与自由文本反馈的应用次序，按钮/文本共用命令校验；补 history_request 原文回查、时间基准、摘要异步 CAS/删除竞争。
- 验收由 32 项补到 44 项（A33～A44），新增场景映射到具体实施项和建议测试文件。保留原有 60 组真实语义样本门槛，未代替开发运行任何业务测试。

## 用户确认的要求
- 模型看到历史用户问答，而非只有当前文本或用户原话。
- 历史带时间戳，记忆有稳定顺序。
- 根据语义回答，支持回顾、纠正、切题，不机械重复流程话术。
- 规划需要考虑多轮记忆问题；当前不以 Mem0 接入为前提。

## 已有依据
- ../2026-09-13_conversation-context-diagnosis/report.md：7 轮实证、可重现故障与数据流。
- ../2026-09-13_conversation-context-diagnosis/mem0-decision.md：Mem0 可后续用于跨会话相关背景检索。
- ../2026-09-12_conversation-memory-design/：已有上下文与跨会话记忆设计，需衔接。
- ../2026-09-13_post-escalation-memory/：存在相近修复任务，文档标记后端完成、前端和观测未完，必须核对源码后再定继承范围。

## 工作区
本轮开始已有 8 个跟踪文件修改，涉及检索评估、模型配置、前端模型说明和 RELEASE；不改动它们。

## 当前源码核对
- contracts/haike_contracts/events.py：事件只有 seq/run_id，没有统一时间字段；快照 user_message 有 at、assistant_message 无时间。
- /messages 只有 text/images/purpose，没有 message_id 或 expected_version；/actions 已有 action_id/version/card 校验。
- 当前 await_input 使用 LangGraph interrupt；普通文本重新进图会清理 pending_card，guide 自由文本统一 rediagnose。解释性追问会破坏等待语义，设计需明确处理。
- 2026-09-13_post-escalation-memory/task_plan.md 标注后端 complete，但 progress 仅记开工；当前 sessions/intake 源码未找到 followup/last_escalation/topics，对其不能认定已交付。已有诊断作为源码基线。
- 旧 2026-09-12 文档的“前端未接通、guide 未实现”已过时；当前代码已有 guide/rediagnose/真实发送。只继承其上下文与幂等设计，不继承旧完成状态。
- 会话默认保留 24h（RETENTION_SESSION_HOURS），本设计不延长；图片与日志按既有策略清理。
- 当前设计选择：跨轮等待放在持久业务 pending 中，各 run 正常结束；用户允许清理历史，因此直接替换现有图并移除旧 interrupt 交互路径。
- 方案明确不将旧升级原因每轮简单清空作为终点；旧风险按主体保留，新决策瞬态。新问题主体不明不能用来绕过同一高危设备限制。
- 用户明确历史可清理、无需兼容；删除按会话固定版本和旧格式迁移设计，改为清理历史后的同版统一切换。

## 最新范围决定
- 不引入 session_protocols，不保留双解码器或新旧双图，不实现旧会话迁移。input_token 直接替换 interrupt_id。
- 清理属于后续实施，当前没有删除数据库数据。范围见 cutover.md；知识库、产品、计划和配置不受影响。
- retention.py 当前核心表清理没有覆盖全部 analytics，CM-02/11 需要补齐；浏览器旧键为 haike.session_id。

## 实施续接核对
- PostgreSQL 图片接收改为 stage → reserve_input 同事务写入；注入图片写入后异常会回滚图片/输入/事件，重试不多写。新增快照视图在行锁内固定公开 checkpoint 与事件水位，清理同事务先锁会话并重新检查活动运行及过期时间。8 项新集成回归通过。
- 新事件契约共 19 种，contracts 74 项通过。共享事件 fixture 重新导出时 seq 都为 1 导致前端只消费第一条；已恢复连续 seq 与独立 event_id，重新检查前端。
- 最终模型预算需要计入结构化 schema 和备用模型；当前系统模板还把动态状态拼进 system，需要将其迁入有来源的数据消息，诊断/步骤/正常回复需接同一 ContextBuilder。
- 官方窗口资料（2026-09-13 查询）：[Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5) 为 1M；[GLM-4.7](https://docs.bigmodel.cn/cn/guide/models/text/glm-4.7) 为 200K；[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing) V4 Flash/Pro 为 1M。其余别名需继续核对，不能凭同厂商假定相同窗口。
- 其余官方窗口：[Qwen3.7 Flash](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[Qwen3.7 Plus](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)、[Qwen3.8 Max](https://help.aliyun.com/zh/model-studio/qwen3-8-max) 均 1,000,000；[Qwen3 VL Plus](https://help.aliyun.com/zh/model-studio/qwen3-vl-plus) 262,144；[Gemini 2.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) 1,048,576；[Haiku 4.5](https://platform.claude.com/docs/zh-TW/models/haiku-4-5/overview) 200K；[GLM 模型总览](https://docs.bigmodel.cn/cn/guide/start/model-overview) Flash 128K。配置只新增窗口值与 intake 输出 1536 预算，保留其他任务正在调整的厂商路由。
- 实际 Router 每次结构化尝试（含 schema 重试提示）和 stream 备用调用前检查文字/schema 8k 上界，并按候选模型窗口预留输出和图片；没有把不同模型写成同一窗口。33 项 conversation 回归已通过，真实语义 gold 评测接续。

- 真实语义第一轮 70/75（93.3%），5 个失败均为 resume_issue 被归为 history_query；已保留 semantic-eval-round1.json。修复提示的“处理旧问题 vs 查询原话”定义，并修复 known target+other 被误开 issue 的 reducer 分支；二轮保持原 gold 期望，不下调门槛。

## Step back 审阅

- 用户最新要求优先于原测试迁移计划：旧版本流程与历史数据不必保留。当前实施与测试取舍见 step-back.md。
- 源码确认：graph.py 当前既有统一 understand，也保留未挂到 build_graph 的 rediagnose、route_after_rediagnose、in_guide 与旧动作分支。它们不应因为旧测试存在而被保留。
- intake 目前并非再次调用旧抽取模型，而是消息/图片登记和 pending 清理节点；审阅需区分误导性的旧命名/注释与实际模型调用，不能声称每轮已经重复调用两次理解模型。
- 新 conversation 测试已经直接覆盖原七轮和解释后反馈闭环，但 pending_flow 仍复用旧 guide 测试 fixture；独立验收需脱离旧协议/模型结果转换器。
- timestamp 与 seq 都需要：前者用于时间理解，后者用于稳定先后顺序。把历史补到 Prompt 并不能代替正确的语义路由和按问题保存状态。

### 新版清理与部署核对

- 新图移除 intake/human_request 两个重复入口节点和旧 rediagnose 路径；新语义入口负责一轮处理，pending 改变由明确决策负责。
- 当前部署是本机 haike Compose，orchestrator 对外 8000，镜像内包含用户前端和管理端。其他 WeKnora 与观测服务也在同一 Compose 项目，不能用 down -v 或全卷 reset 清理会话。
- conversation_config 原本按源码相对路径查配置，容器内会误查 /config；已新增环境路径覆盖，Docker 指向 /srv/config/conversation.yaml。
- 用户最新明确要求完成后部署和重启，无需再次确认。历史清理只针对应用会话及派生数据；保留其他数据库、产品、知识和计划数据。
