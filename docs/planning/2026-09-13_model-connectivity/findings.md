# Findings

- 2026-09-13 本机 /health：db/redis/weknora 正常，当前 domestic；DeepSeek、智谱有 key，Anthropic、通义、Google 缺 key。
- 原聚合检查要求通道所有厂商都有 key，不等于业务可用；Composer offline=false，不受健康灯阻塞。
- ModelRegistry.build 已统一模型 SDK/参数，默认 SDK 重试为 0；CLI 的简短提示可复用。
- app.state.model_registry 在 FastAPI lifespan 初始化，适合作为单一配置来源。
- 当前工作区已有配置、部署等未提交修改；本任务不覆盖这些修改。
- 仓库只有根 AGENTS.md，无 CONTEXT.md 和区域 ADR。
