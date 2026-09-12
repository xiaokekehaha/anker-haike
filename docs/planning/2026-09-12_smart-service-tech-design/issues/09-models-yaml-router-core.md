# 09: models.yaml 加载、校验与别名路由

**What to build:** 编排服务启动时加载模型配置：解析 providers / models / lanes，校验每个 task 在默认通道下有链、别名存在、需视觉的任务链上模型都支持视觉。别名通过 LangChain 统一入口建实例，国内厂商走 OpenAI 兼容 base_url。附带一条命令从配置生成路由展示表。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** in-progress

**Owner:** Claude Code B（模型层线，2026-09-12 认领；改动范围 `orchestrator/app/models/`、`orchestrator/scripts/`、`config/models.yaml`、orchestrator 依赖；不动 `orchestrator/app/sessions/`、`contracts/`、`frontend/`）

- [ ] 配置缺失或不一致时启动失败并指出具体项
- [ ] MODEL_LANE 环境变量切换默认通道
- [ ] 生成的路由表与 model-selection 第 4 节格式一致
- [ ] 有 CLI 可对任一 task 发一次最简调用并打印命中模型与延迟
- [ ] API key 只从环境变量读取，不进日志
- [ ] 仓库根目录 .env（已 gitignore）提供 DEEPSEEK_API_KEY 作为默认测试厂商；CLI 探测脚本无其他 key 时默认走 deepseek 别名

**设计依据：** model-selection §3.5、§3.7
