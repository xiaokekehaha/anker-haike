# 工作记录

## 2026-09-12
- 起步时发现另一个 Claude Code 会话（A）同时在收尾票 03，contracts/tests 被互相覆盖；本会话让出 03/05/07，改走模型层线 09–12，并在总计划 task_plan.md 写入三方分工。
- 票 09：新增 langchain 1.4.0 + langchain-openai / anthropic / google-genai 依赖；写 config.py（Pydantic 结构 + 汇总式一致性校验）、registry.py（别名 → init_chat_model，max_retries=0，effort 映射，key 不进日志）、route_table.py、cli.py（haike-route-table / haike-model-probe）。
- 校验发现 ChatAnthropic 有显式 `output_config` 字段，改为直接传参而非 model_kwargs（否则 LangChain 告警）。
- models.yaml：providers 加 `lane`；填 deepseek-chat 与两个 Anthropic id，其余 TBD。
- 实测：`make route-table` 与 model-selection §4 表一致；`make model-probe TASK=intake` 命中 deepseek/deepseek-chat 约 2.7 s 返回「收到」；坏配置 / MODEL_LANE=mars 时 uvicorn 启动失败并逐项列出问题；正常启动日志只含 key set/missing。
- 后端 36 项测试、ruff 通过。票 09 标 done。
- 票 10：router.py（三策略 + 统一校验 + 带错误重试 + attempts）、fake.py（脚本化假模型，记录 tags / metadata / bind 参数）。真实验证（scratch 脚本，DeepSeek）：json_object 与 tools 均 1.3 s 解析出相同结果；json_schema 被 DeepSeek 拒绝（400），router 正确换下一家。56 项后端单测、ruff 通过。票 10 标 done。
- 票 11：router.py 增加异常分类、拒答检测、退避（可注入 sleep / rng / clock）、能力跳过、预算截止；fake.py 支持 AIMessage 脚本项。13 项新单测，后端共 69 项通过。票 11 标 done。
- 票 12：queue.py 有界门 + CapacityExceeded → recoverable error 字段；429 指数退避 1/2/4 s 受预算约束；结构化日志与 snapshot。7 项新单测，后端共 76 项通过，ruff 通过。票 12 标 done。模型层 M2 的 09–12 完成。
- 票 19：config/products.yaml（21 SKU，含 S1 Pro 同名异类）、app/catalog（三级匹配 + L4 缓存 + products 表 upsert）、haike-seed CLI；`make seed` 本机 Postgres 写入 21 条，重复执行一致。20 项单测。
- 票 31：config/plans.yaml（5 计划 + evidence 索引）、app/plans（模型校验、next_on 规则推进、L4、Schema 枚举、plans 表 upsert）；坏 next_on 时 uvicorn 启动失败实测。18 项单测。后端合计 120 项通过，ruff 通过。
- 票 15：config/rules/safety_terms.yaml、app/rules/service.py（热加载、check_in、结构化日志）；graph.py intake 末尾接 CP-in，命中经条件边进 escalate 节点。测试含「首句冒烟 → progress 只有 intake / escalate、假 router 零调用、safety_flags 形状」。17 项单测。
- 票 26：拉取 WeKnora v0.8.0 固定 commit 的 docs/api（knowledge-base / knowledge / faq / knowledge-search / tenant / model / auth）核对字段；写 data/knowledge 模拟数据、weknora_client / ingest / snapshot / cli、builtin_models.yaml 与 compose 挂载。内存版 WeKnora（MockTransport）11 项测试通过；本机 WeKnora 只做了 auth_config 与 401 路径 smoke。真实注册 tenant 与百炼 key 属账号 / 密钥操作，留给用户执行 `make kb-bootstrap`、填 DASHSCOPE_API_KEY 后 `make kb-ingest`。后端合计 152 项单测、ruff 通过。
- 票 26 实测：`make kb-bootstrap` 注册 tenant 10001，key 需经 /tenants/{id}/api-keys（full_access）创建；加 SSRF_WHITELIST_EXTRA、修 status=publish、custom_metadata 标量化后，用 deploy/dev/embedding_stub.py（host:8099）登记 Embedding 模型，`make kb-ingest` 3 手册 + 200 工单全部 completed，二次 / 三次导入 0 新建 203 跳过，`kb-verify` 元数据可查，`kb-search` 有结果，`kb-snapshot` 导出。票 26 标 done。
- 票 27：IV-1 实测（knowledge-search 忽略 knowledge_ids、hybrid-search 遵守、空列表=不过滤），adapter.py 四态 + 允许集合 + 后过滤 + 截断 + counter_evidence；11 项测试含本机集成。标 done。
- 票 16 后端：escalation/summary.py 纯规则渲染摘要，graph escalate 节点发安抚消息 + escalation_summary；全链路事件序列与快照折叠测试通过。前端 SummaryCard 留给 Codex。后端合计 172 项单测。
- 本机后台仍运行 embedding 桩（uvicorn :8099）；重启机器后需 `cd orchestrator && uv run uvicorn --app-dir ../deploy/dev embedding_stub:app --port 8099` 再跑 kb 命令。
- 票 17：app/prompts（三层系统提示、<data> 包裹、PROMPT_VERSION）、app/intake（IntakeExtraction、规则映射 strategy、降级）、app/models/runtime（进程级 Router，HAIKE_LLM=off 单测默认关）；graph.py intake 节点 CP-in 后调用抽取，wants_human → R3。金标 fixture 4 条（假 router 4/4，真实 DeepSeek 2/4 通过 2 条连接错误跳过）。
- 票 28：graph.py retrieve 节点 + app/knowledge/runtime（进程级适配器，HAIKE_KNOWLEDGE=off 单测默认关）；tool_call / evidence 事件、knowledge_status、evidence 累积。改了 A 的一条 resume 测试断言（忽略 tool_call）。真实端到端（uvicorn + 真 DeepSeek + 真 WeKnora）：X9 Pro 话术 → 抽取 anxious → 检索命中 10 条且全在允许范围 → done v5，timeline [user_message, tool, evidence]。后端 207 项单测通过（2 skip 为 DeepSeek 瞬时连接错误）。
- 票 13 / 14 / 18：ModelRouter.stream（start/delta/aborted/switched/end，未吐字失败静默重试、吐字后失败 aborted + 替换、简化 Prompt 变体、primary 以首家真正调用为准）、sessions/streaming.py 映射 message 事件并记 first_visible_ms、prompts/reply.py 模板文件化、graph.py reassure 节点与 reply 节点真实流式回复。FakeChatModel 支持流脚本与断流注入。models.yaml domestic reply.stream 链尾加 deepseek。真实 DeepSeek + WeKnora：A2 安抚句先于卡片（907 ms）、A1 回复引用滚刷清理片段（828 ms）。后端 223 项单测通过。
- 全量回归时发现 6 项失败均为 A 会话票 24 进行中（零命中改澄清追问）导致其自身旧断言失效，非 B 改动；B 仅把 test_rules 平稳路径的话术改为已确认产品。B 自己的模块（models / knowledge / rules / intake / prompts / escalation / streaming）全部通过。
- 票 29：app/images（Postgres bytea + sha256、5 MB / mime 校验、1 h 清理循环）、/messages 多部分 images、GET /sessions/{id}/images/{image_id}、状态 image_refs、contracts UserMessageItem.images + 前端类型重生成；前端 lib/image.ts、Composer 附件（压缩 / 内联拒绝 / 预览）、UserBubble。后端 7 项（含真实 Postgres）、前端 7 项测试，build 通过。
- 票 32：app/diagnose（query / rewrite / synthesize / config）+ graph retrieve 流水线 + retrieval.yaml + query.rewrite 路由；24 项单测。真实 DeepSeek + WeKnora A1：plans_ranked 首位 rv_suction_hair_wrap 0.9，引用手册 c12 与同型号工单。修了 `**plans` 覆盖 trace、枚举 schema 让整批作废、CATEGORY_LABELS 漏导入三处 bug。后端合计 275 项通过。
- 票 33：config/fault_cards.yaml + app/faultcards（≤800 token 校验、命中、证据）、graph 降级路由（evidence / fault_card / standard_flow / R5）与 guide_entry；`make seed WHAT=fault_cards` 5 行。调整了 test_retrieve_events / test_sessions_actions 对末阶段的断言（diagnose → guide）。后端 297 项通过。用户要求票 30 先用 mock 视觉 provider，真实 DASHSCOPE key 后补。
- 前端集成：state/reducer（纯函数，fixtures 15 事件）、api/sse + client、useSession（sessionStorage、15 s 提示、deadline+5 s 断流恢复、409 快照重建、取消、请求人工）、组件 AssistantBubble / ToolRow / EvidenceDrawer / ProductCard / StepCard / ReceiptCard / SummaryCard / Toast / Timeline，App 接线去掉只读壳。71 项 vitest、typecheck、build 通过。票 06 done，13/14/16/28 的前端部分补齐标 done。
- 票 30 撞车：A 已实现 vision 节点并提交（含 image_limit / select_images / 无视觉降级），B 覆盖了其 vision.py 并在 retrieve 重复读图；已 git checkout 回退 A 的文件、删掉重复块，只保留 retrieve 内「vision_status=ok 的观察项优先占用补检索名额」。A 的 test_vision / test_vision_graph 恢复通过。教训：认领前先 `git log --oneline -5` 与 `git status`，A 的提交节奏很快。
- 浏览器端到端（FastAPI 托管 dist，真实 DeepSeek + WeKnora）：焦急话术先出安抚句 → 工具行「检索知识库 · 命中 10 条来源」→ 来源抽屉 → 流式回复引用手册步骤 → 进度到「分步排障」。
