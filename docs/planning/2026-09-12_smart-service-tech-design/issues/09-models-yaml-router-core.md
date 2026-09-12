# 09: models.yaml 加载、校验与别名路由

**What to build:** 编排服务启动时加载模型配置：解析 providers / models / lanes，校验每个 task 在默认通道下有链、别名存在、需视觉的任务链上模型都支持视觉。别名通过 LangChain 统一入口建实例，国内厂商走 OpenAI 兼容 base_url。附带一条命令从配置生成路由展示表。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线，2026-09-12 认领；改动范围 `orchestrator/app/models/`、`orchestrator/scripts/`、`config/models.yaml`、orchestrator 依赖；不动 `orchestrator/app/sessions/`、`contracts/`、`frontend/`）

- [x] 配置缺失或不一致时启动失败并指出具体项（`app/models/config.py` 汇总全部问题一次报出：文件缺失、YAML 行列、字段类型 / 多余字段、未知别名、厂商引用、needs_vision 链上非视觉模型、默认通道缺 task、无 embedding / rerank 别名、链长超 chain_max；uvicorn 实测 `Application startup failed` 退出码 3）
- [x] MODEL_LANE 环境变量切换默认通道（未定义通道名启动失败并列出可选项）
- [x] 生成的路由表与 model-selection 第 4 节格式一致（`make route-table [LANE=]`，跨通道别名标注「（overseas）」，含 embedding / rerank 行）
- [x] 有 CLI 可对任一 task 发一次最简调用并打印命中模型与延迟（`make model-probe TASK=intake [ALIAS=]`；实测 `OK model_used=deepseek/deepseek-chat latency_ms≈2.7 s`）
- [x] API key 只从环境变量读取，不进日志（`ModelRegistry.describe()` 只报 set / missing，单测断言 key 不出现在日志字典；异常信息只含环境变量名）
- [x] 仓库根目录 .env（已 gitignore）提供 DEEPSEEK_API_KEY 作为默认测试厂商；CLI 探测脚本无其他 key 时默认走 deepseek 别名（`pick_probe_alias`：显式别名 > 链上首个可用 > deepseek）

**设计依据：** model-selection §3.5、§3.7

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/models/`（config.py 结构与校验、registry.py 别名 → `init_chat_model` 实例与 effort 参数映射、route_table.py、cli.py）；`app/main.py` lifespan 加载并挂 `app.state.model_registry`；依赖新增 langchain 1.4 / langchain-openai / langchain-anthropic / langchain-google-genai；36 项单测。`config/models.yaml`：providers 增加 `lane` 字段标注通道；已填 id：deepseek-chat、claude-sonnet-5、claude-haiku-4-5-20251001，其余仍 TBD（启动不报错，调用时按未配置跳过，票 42 冻结）。effort 映射：Claude 传 `output_config.effort`，其他厂商 temperature low/medium/high = 0 / 0.2 / 0.3。health 的 `check_models` 仍自行读 yaml，未改动（票 44 可统一）。
