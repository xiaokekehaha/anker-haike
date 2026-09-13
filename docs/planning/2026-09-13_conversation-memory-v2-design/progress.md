# 进展
- CM-01 基线样本完成：75 条合成语义 gold 首轮 70/75，补齐 resume 定义和已知实体复用后二轮 75/75；首轮输出保留为 semantic-eval-round1.json。其他运行与泛化验收仍未完成。
- CM-09：每会话单任务原话摘录缓存已接入，完整问答带 ID/时间；CAS 绑定发布 checkpoint，派生写入不续期，纠正 revision 变化拒读，删除后迟到写入不复活会话。内存/真实 PostgreSQL 3 项通过。
- CM-02/07：移除外部 rediagnose，卡片动作要求目标 issue，request_human 在取消前校验目标；前端保留不确定发送的 input_id/草稿，按快照 last_event_seq 续接，纯图片不伪造用户文本。
- CM-08：管理员新节点、语义/补丁计数记录已接，展示改为“需人工处理”；内部提交事件独立 schema；迁移 0005 SQL 冻结，清理覆盖新账本、摘要及相关 analytics。没有清理或发布正式会话。
- 本次更新规划的内联 Python 再遇输入编码错误，未写入；改为 apply_patch。新上下文/前端重试测试仍在运行。
- 2026-09-13 开发交接审阅完成：新增 developer-handoff.md，并同步总体设计、数据协议、实施计划、清理切换、README 与自检记录。重点补齐公开版本与 checkpoint 解耦、提交/恢复故障表、pending 挂起/替代 token、知识引用解析与旧证据失效、最终模型输入预算、前端所有等待阶段可交谈。新增 A33～A44，验收合计 44 项。脚本检查 11 份 Markdown、23 个本地文件链接、9 项需求、11 项实施编号、44 项验收编号及围栏闭合全部通过；未渲染 Mermaid，未运行业务测试/迁移/清理/部署。审阅期间其他开发任务推进的源码和 CM 状态保留，未将其测试记录算作本次验证。
- 2026-09-13：按用户要求开始开发交接审阅，只修改本目录规划。当前工作树另有模型、检索评测和前端文件变更，保留其内容与实施进度；优先核对多轮上下文、知识引用、pending、提交恢复和契约生成。
- 2026-09-13：恢复前序诊断规划；建立独立 V2 设计目录；读取事件/动作/快照契约，发现相近 post-escalation 任务记录，正在核对。
- 完成 README、总体设计和数据协议。初版包含按会话固定协议与双读回退，已由下方用户最新决定替代。
- 完成实施计划（CM-01～CM-11，全部未开始）和验收矩阵（A01～A32，R01～R09 全覆盖）；定义确定性/真实语义/集成/UI 四类验证及候选发布门槛。
- 完成初版文档自检：11 个本地链接有效，9 个需求全部映射，11 个实施项和 32 个验收场景编号完整。初版灰度方案已取消，业务实现仍未开始。
- 用户追加：历史可以清理、不考虑兼容。已重写总体设计、数据协议、实施计划及 A26/A32；删除双协议、旧 reader、双图、引擎分配表，补充 cutover.md 清理范围与同版切换。未执行删除。
- 最新自检通过：10 份 Markdown、14 个本地链接、9 个需求、11 个实施项、32 个验收场景；主设计无过时的双协议或双图设计。规划全部完成，业务实现和历史清理未执行。
- 用户启动开发目标：开发直到完成，历史会话记录可清理。已重新核对工作树并开启 CM-01；其余实施项待推进，不以规划完成代替开发完成。
- CM-01 基线：43 项中 32 通过、11 失败。失败均为已有测试模型 registry 无 zhipu 路由，完整日志见 baseline.log，需在新契约测试迁移时修正测试隔离。
- CM-02 开始：新增 session_inputs 接收事务及内存等价实现；5 个回归覆盖并发同 ID、正文冲突、旧 version 重放、无半条写入、删除账本，通过。初次红灯为新模块不存在，随后实现后转绿。
- 已接通消息/动作共用接收账本（input_id、expected_version）、event_id/recorded_at、input_received；request_human 重放在取消之前检查。新增 Alembic 0005，但尚未运行迁移/清理/发布。
- 新增完整事件历史折叠和有预算的整轮上下文，保留角色、时间、来源、aborted/replaced，当前输入仅出现一次。新增统一语义解释器、增量 fact reducer、多 issue 状态投影、独立风险记录与本轮 decision。
- 当前图已改为 START→understand→业务节点→commit_issue→END，卡片等待成为持久业务状态；摘要只使用当前有效事实，带独立 revision，当前无真实人工连接时只称“已整理”。
- 前端发送新协议，卡片等待期间允许文字追问；已增加时间、按钮记录、历史摘要版本和已替换回复标记。契约 Schema/TS/Zod 已生成；旧测试夹具迁移进行中。
- 新增 16 项单元/端到端回归通过，覆盖完整问答、并发幂等、风险归属、否定/纠正、保留待办与步骤计数、纯状态投影。尚未完成 PostgreSQL 事务验证、全量旧业务回归迁移、长历史压缩、崩溃恢复、真实模型语义验收与运行发布。
- 校验发现：新增协议导致旧 TS 夹具缺事件/摘要元数据；已补数据并移除误加到 analytics / cancelled_run 的事件字段。Ruff 首轮 55 项（导入、dict 写法、未用变量）已自动修正。
- 读取同步更新的 developer-handoff.md：采用明确的已发布业务 version 与 published_checkpoint_id，不再以 LangGraph step 作为公共版本。接收账本增加 base_version/base_checkpoint_id；publish_commit 与 done/输入终态/释放 active_run 分别事务化。快照读取已发布的精确 checkpoint。
- 确定性输出随候选节点保存 pending_effects，commit_issue 后发布；稳定 event_id 查重并校验正文，恢复已提交结果不再调用模型；提交前中断直接标失败，保留输入原话。新轮从已发布 checkpoint 开始，未提交候选不继承。
- 当前回复生成先完整保存在候选输出后发布，progress/tool 状态仍实时；这一实现优先保证提交一致性，真正 token 首出延迟和最终预算仍需测量/优化，不能宣称满足全部运行指标。
- 新增恢复两项测试，基础会话测试共 18 项通过。前端 typecheck 通过；orchestrator 完整测试可收集 578 项，尚未执行全量回归。历史清理、迁移、发布仍未执行。
- 协议夹具迁移后：contracts 70 项通过，frontend 178 项通过，真实项目 PostgreSQL 临时 schema 下 2 项并发事务测试通过（隔离 schema 已清理）。没有迁移或清理正式会话。
- 加入自然语言回答待办的受控命令解析：反馈须有本条原话和明确结果，复用原 input_id/card/token；“做过了”、无原话依据、纠正同时反馈不会误计步骤。新增 3 项通过。
- 历史回查新增 first/reference/time_range；30 轮后按原始记录找回最初问答、拒绝未来/不存在引用，3 项通过。动态事实和问题索引移出 system 高权限提示层，按数据消息装配。
- 真实 intake 冒烟调用成功：dashscope/qwen3.7-flash 将“我的耳机没有声音”识别为 report_problem，抽取症状与原文来源；此仅单条连通验证，不等于 60 条语义评测通过。
- 启动已有后端回归的离线检查（MODEL_LANE=domestic，数据库端口指向不可达地址以跳过非隔离历史清理测试）；目标是定位旧接口/模型夹具与新协议的差异。真实事务覆盖由上述隔离 PostgreSQL 测试独立提供。
- 前端旧夹具迁移收尾：sse/reducer/useSession/Composer/App.receipt-flow 五个文件改完，`npx vitest run` 20 文件 178 项全通过，typecheck 与 contracts:check 通过。其中 SSE 与 escalation_summary 夹具补 event_id/recorded_at 与摘要元数据；replaces 断言改为"保留旧气泡并标 replaced"；等待 select_product/confirm_receipt/upload_receipt 的输入禁用断言按交接契约 §7、验收 A35 改为允许纯文字追问（凭证纯文字也可发送）；useSession 取消请求体误被夹具脚本加进 event_id/recorded_at，已还原为 {run_id}。orchestrator 全量回归仍是 152 失败 / 425 通过，主因是旧断言缺 active_issue_id、issues、last_event_seq、latest_summaries 等新快照字段，未处理。

- 补充 issue 草稿、切换挂起/恢复替代 token 和 pending_changed 事件；修复无效风险原文引用绕过预检的分支。原七轮断言由“两问题”更新为“两已描述问题+一待描述草稿”，先前失败已确认是新需求预期变化。前端新增问题入口已接通，typecheck 通过；新增回归进行中。
- CM-03/06：各图节点模型调用接入统一会话上下文；动态状态移出 system，新增 conversation.yaml 与时间区配置；token 估算改为 o200k + 25% 裕量。诊断新检索单独维护 current_evidence_ids，普通回答不再取累计证据前六条；图像观察转换为有输入/图片来源的事实，图像危险信号保存独立 RiskCase。型号纠正保留同 DeviceRef/计数、使旧产品依据失效。全量新会话回归待本轮结果。
- 最新前端 20 文件 180 项通过；contracts 74 项通过；原七轮、整轮历史和真实步骤闭环 6 项通过。尚未执行发布与旧历史清理。
- 真实语义评测扩到 75 条（15 类×5），期望先于模型运行编写；使用合成两问题上下文，不向模型发送正式会话。首次夹具生成误用系统 Python 缺 PyYAML，改用项目 uv 环境后启动。模型别名窗口已添加，Router 最终预算检查已接入；尚待真实结果。
- 续接验证：38 个新会话用例加 7 个图片用例共 45 项通过，前端 181 项通过。修复图片引用在历史快照丢失、情绪策略未映射和 analytics 运行序号多加一次；恢复夹具补齐 issue_changed 新字段。
- 凭证待办保存 collection_reason，上传/确认/跳过直接依待办继续，不依赖旧的全局升级原因。替换凭证只保留新图并清旧 OCR 核实结果；此分支待专门回归。补充会话 detail_level 偏好与带来源的后置风险限制，摘要缓存超预算时先丢弃可选缓存。一次补丁因同一路径重复操作被拒绝，合并文件操作后成功，无半写入。
- 主流程回归最新 93/102 通过，9 项中 2 项是测试替换误伤状态码（已修复）；其余为新卡 ID/token、已消费卡不重发、摘要只使用有效事实及多模态数据位置变化的旧断言。凭证与新会话合并 70/71 通过，最后一项为旧 receipt_card 重发预期。
- 卡片身份加入 input_id+issue_id，同一模型/步骤重新开卡不再覆盖历史位置；卡片事件和 pending 带 issue，发布 active/consumed/invalidated 事件。重复症状不再无条件作废待办；型号纠正已有明确线索时不再追问“哪句说错”。

### Step back：停止旧测试迁移

- 用户指出旧版本测试工作过多，明确旧流程、旧数据可以不用。停止原 Next Step 的旧测试迁移，不再修改旧节点/版本/动作断言以追求历史全量通过。
- 核对 graph.py：当前已经 START→understand，但仍存在未注册的旧 rediagnose 函数、apply_action 的旧 rediagnose 分支、in_guide 和旧 interrupt 注释；intake 还承担历史消息/图片记录和待办清理，职责需要收敛。此处是清理依据，尚未删除。
- 新增 step-back.md，实施收敛为 S1 唯一主链路、S2 六组用户场景、S3 新会话切换；同步 README、task_plan、implementation-plan、developer-handoff 的阅读优先级和验收取舍。
- 新测试应直接使用新语义输入，不继续依赖旧抽取 schema 转换器。原始七轮交互保留为需求样本，旧系统的错误输出不作为预期。
- 本次 Step back 只作审阅和规划调整，未运行新的业务测试，未删除代码、数据库或其他任务改动。此前已启动的幂等/冲突/取消流检查已结束，13 项通过；该结果不代表整项开发完成。

### S1：单入口清理

- 前一目标轮已改变实施依据，归类为规划进展；本轮开始实际源码清理。删除旧 rediagnose 模块、未注册图函数、外部动作分支及其旧专用测试；删除 intake/human_request 两个重复入口节点，统一从 understand 选择直接回答或业务能力。
- 消息/图片引用在统一入口登记；待办仅由语义/命令决策改变，不再被旧 intake 无条件清空。动作沿用账本 received_at，避免步骤操作重新刷新时间基准。
- 新增 conversation_runtime.py，直接使用严格的新语义 schema、真实 Router/图/规则/计划，通过 HTTP 驱动；只替换模型与知识 I/O。解释后反馈场景已脱离旧 guide 测试和旧语义转换器。
- 取消测试改为在摘要节点注入明确等待点，不依赖已删除的旧 intake 节点时序。启动新 conversation 套件；尚未记录通过结果。
- Ruff 首轮修正 4 个未用导入，另一个 pytest fixture 重导入告警通过显式 re-export 修复，待复验。

- 首轮单入口清理后新会话 38 项通过。新增基于真实 HTTP 的刷新顺序、取消保留待办、发布中 503、断线续接和旧动作拒绝验证后，新会话 44 项通过（含项目 PostgreSQL 隔离 schema）。没有将旧模型/旧协议转换夹具用于这些验证。
- 删除 session_actions 存储 API、独立 try_start_run/finish_run、重复 finish_input 和旧 checkpoint-version 函数；恢复只接受输入账本中的 run。0005 迁移会移除旧动作表，尚未运行正式迁移。
- 删除旧 test_sessions_store_pg/snapshot/resume/cancel 文件；对应新协议事务与恢复行为由 test_conversation_inputs_pg/recovery/lifecycle 覆盖，不再迁移旧节点边界或旧事件格式断言。
- 快照删除重复消息/工具折叠，统一使用带来源的历史折叠；修复 evidence 的时间/排序以及前端 input_received 图片引用丢失。前端此前 181 项通过，新增图片/证据历史用例待最终构建验证。
- 本轮一次前端补丁因同文件上下文顺序错误未应用，按顺序重发成功。生产会话模块、清理模块与新闭环测试的 Ruff 已通过；其他新测试早前的格式告警尚需统一格式化，不属于业务失败。
- 用户进一步授权大胆清理历史信息，完成后部署并重启。已核对当前本机 Docker Compose 服务；部署对象是 orchestrator（内置前端），WeKnora/产品知识数据保留。构建新镜像进行中，未停止或清理正式服务。
- 修复容器会话配置路径，Docker 设置 CONVERSATION_CONFIG_PATH；构建时预热 tiktoken 缓存，固定单 worker；shutdown 等待运行任务取消完成后才关闭连接池。
- 长对话真实入口回归发现第 15 轮起语义降级：interpret 的 ContextBuilder 未预留结构化 schema，而 Router 计入 schema，导致模型请求被预算拒绝。已统一预留 schema + 256 token，并在新 HTTP 夹具逐轮断言真实语义模型调用；待复验。凭证新场景两项通过。
- 新版会话 47 项、前端 182 项、契约检查通过；镜像 061523d842c8 构建完成。正式清理已完成（794 会话，产品/计划等计数未变），服务已首次重建启动。
- 部署真实首轮发现正式库此前已标记草稿版 0005，但 session_inputs 缺 base_version，自动迁移因此跳过；并非健康检查能发现的问题。停止服务后重新创建可清理的新账本/摘要表并应用最终 0005 DDL，不保留草稿结构兼容。
- 更正前文推测：应用分析 schema 实际是 analytics；已精确清理这六张表。此前查询 analytics/db.py 与 app/health.py 不存在，已改读实际 schema.py/health/router.py。

### 交付完成
- 原案例真实模型九轮通过，conversation_turn 均为 source=model：历史回顾、更换问题、人工摘要、模糊纠正及恢复耳机问题均按语义响应；控制轮未重复生成升级摘要。
- 浏览器实际完成 X9 Pro 知识检索出卡 → 追问解释 → 刷新恢复有时间戳的完整问答与原卡 → 跳过原卡后出现第二步。修复追问结束时实时进度与刷新后阶段不一致的问题，补充定向断言通过。
- 首页人工承诺、步骤等待提示与实际能力对齐；回复提示禁止内部记录标识。保留其他任务的键盘交互改动。
- 最终镜像 eb76a7525f85 已部署并 force-recreate，健康正常；旧 session_actions 为 None，原 49e8168c9175 事件为 0；revision 0005。
- 最后重启恢复真实会话 version 9，完成第 10 轮回顾，首条原始问答时间/来源未变。最后前端 182 项通过；新会话 47 项通过；阶段定向 1 项通过；契约与 typecheck 通过。
- S1/S2/S3 均完成。交付文档 delivery.md 区分了编排夹具、真实模型、浏览器检查的证据，并保留实际支持范围说明。未运行/迁移全部旧版本流程测试，未提交 git 或覆盖其他任务改动。
