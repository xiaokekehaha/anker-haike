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
