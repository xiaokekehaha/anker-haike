# 模型层线（票 09–12，Claude Code B）

## 目标
在 `orchestrator/app/models/` 内完成 ModelRouter 全部基础：配置与路由（09）、结构化 invoke（10）、降级链与预算（11）、限流退避与有界队列（12）。与会话骨架线（Claude Code A：03/05/07/08）和前端线（Codex：04/06）并行，不改对方目录。

## 阶段
1. 票 09 models.yaml 加载、校验与别名路由 — complete（36 项单测；uvicorn 启动失败路径实测；DeepSeek 真实探测通过）
2. 票 10 结构化 invoke：三种输出策略与 Pydantic 校验 — complete（9 项单测；DeepSeek 真实 json_object / tools 通过）
3. 票 11 降级链与 task 预算 — complete（13 项单测，注入时钟 / sleep）
4. 票 12 限流退避与全局有界队列 — complete（7 项单测）
5. 票 19 产品目录表与匹配服务 — complete（20 项单测，Postgres seed 实测）
6. 票 31 预写排障计划表与 seed — complete（18 项单测，Postgres seed 实测）
7. 票 15 规则服务骨架与 CP-in — complete（17 项单测；graph.py 追加 CP-in 与 escalate 条件边）
8. 票 26 WeKnora tenant 与知识入库 — code-complete（11 项内存版测试；真实 tenant 注册与百炼 key 待用户提供）
9. 票 13/14 依赖票 05 的 SSE 流，待与 A 协调归属

## 协作边界
- 只改：`orchestrator/app/models/`、`catalog/`、`plans/`、`rules/`、`knowledge/`、`seed_cli.py`、对应 tests、`config/*.yaml`、`config/rules/`、`data/knowledge/`、`deploy/weknora/`。票 15 例外：向 `app/sessions/graph.py` 追加 CP-in（已告知 A，非安全路径行为不变）。
- 共享文件只追加：Makefile（模型层小节）、orchestrator/pyproject.toml（依赖与 scripts）、app/main.py（lifespan 两行）。
- 不动 `contracts/`、`orchestrator/app/sessions/`、`frontend/`。

## Next Step
09–12、19、31 完成（后端 120 项单测）。剩余无阻塞且不在他人目录的票：26（WeKnora tenant 与入库，依赖票 01，需要百炼 embedding key）。票 15（规则服务骨架）依赖 05 已完成，可与 A 协调认领。原说明：票 13（stream 入口与 message 事件）、14（流式中断切换）依赖票 05 的 SSE 通路：待 Claude Code A 完成票 05 后，由 B 认领 13/14 中 `ModelRouter.stream` 的模型侧实现，API 层事件映射与 A 协调。期间 B 可接只依赖票 01 的 19（产品目录）、31（plans 表 seed）。

## 已完成说明
票 10：`ModelRouter.invoke(task, messages, schema, budget_ms)`，按 `structured` 能力选 json_schema / json_object + schema 提示 / tool calling，统一 Pydantic 校验，失败带错误重试一次；tag=internal，metadata 含 task / session_id / lane；DeepSeek 走 json_object 实测。
