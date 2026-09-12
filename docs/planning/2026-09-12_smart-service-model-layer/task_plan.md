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
8. 票 26 WeKnora tenant 与知识入库 — complete（本机 WeKnora 实测：tenant 10001、3 手册 + 200 工单 completed、幂等、快照；embedding 用本机桩）
10. 票 27 KnowledgeAdapter — complete（IV-1 实测：hybrid-search 遵守 knowledge_ids；11 项测试含本机集成）
11. 票 16 升级摘要 — 后端 complete，SummaryCard 前端待 Codex
12. 票 17 intake 抽取与情绪 — complete（金标 4 条；真实 DeepSeek 端到端）
13. 票 28 tool_call / evidence — 后端 complete，EvidenceDrawer 前端待 Codex
14. 票 13 stream 入口 — 后端 complete（AssistantBubble sanitize 待 Codex）
15. 票 14 流式中断切换 — 后端 complete（前端替换 / 标注待 Codex）
16. 票 18 安抚句先出与 <data> — complete
17. 票 29 图片上传与会话期存储 — complete（后端 + 前端组件；App 接线属票 06 集成）
18. 票 32 假设汇总 plans_ranked — 核心 complete，读图并行 / 取消晚到 / 人工对照报告留票 30 / 38 / 42
19. 票 33 知识降级 R5 与故障卡 — complete（guide 步骤卡在票 34）
20. 前端集成（票 06 + 08/13/14/16/21/28/29 前端）— complete（71 项 vitest、typecheck、build）
21. 票 30 读图 — 由 A 会话实现并提交（vision 节点 + 无视觉模型降级）；B 曾误写重复实现已回退，只保留「图片观察优先占用补检索名额」。真实 qwen-vl 验证待 DASHSCOPE_API_KEY
9. 票 13/14 依赖票 05 的 SSE 流，待与 A 协调归属

## 协作边界
- 只改：`orchestrator/app/models/`、`catalog/`、`plans/`、`rules/`、`knowledge/`、`seed_cli.py`、对应 tests、`config/*.yaml`、`config/rules/`、`data/knowledge/`、`deploy/weknora/`。票 15 例外：向 `app/sessions/graph.py` 追加 CP-in（已告知 A，非安全路径行为不变）。
- 共享文件只追加：Makefile（模型层小节）、orchestrator/pyproject.toml（依赖与 scripts）、app/main.py（lifespan 两行）。
- 不动 `contracts/`、`orchestrator/app/sessions/`、`frontend/`。

## Next Step
09–19、26–29、31–33 与前端集成完成，13/14/16/28 含前端部分完成（后端 310 项、前端 71 项测试；浏览器端到端：A2 安抚句先出、A1 检索 + 引用回复进入 guide）。A 正在做 39/40（凭证）；B 候选：34（步骤卡下发 guide.step，plan_cursor 已就位）、35（反馈推进）、42（bake-off，需各家 key）。DASHSCOPE_API_KEY 到位后：填 qwen-* / embed / rerank 真实 id，重跑 kb-ingest 与票 30 样本。候选：24（product_state 三分与追问上限 R7，依赖 21）、29（图片上传）、30（读图 diagnose.vision）、32（synthesize plans_ranked，依赖 28/30/31）。候选：18（安抚句流式先出，依赖 13 的 stream 入口——13 仍未有人认领，可由 B 接 13 → 14 → 18）、24（product_state 三分 / 追问上限，依赖 21）。原说明：下一批候选：28（tool_call / evidence 事件，依赖 27，EvidenceDrawer 前端部分需 Codex）、17（intake 抽取，依赖 10/15）、24（product_state 三分，依赖 21）。原说明：剩余无阻塞且不在他人目录的票：26（WeKnora tenant 与入库，依赖票 01，需要百炼 embedding key）。票 15（规则服务骨架）依赖 05 已完成，可与 A 协调认领。原说明：票 13（stream 入口与 message 事件）、14（流式中断切换）依赖票 05 的 SSE 通路：待 Claude Code A 完成票 05 后，由 B 认领 13/14 中 `ModelRouter.stream` 的模型侧实现，API 层事件映射与 A 协调。期间 B 可接只依赖票 01 的 19（产品目录）、31（plans 表 seed）。

## 已完成说明
票 10：`ModelRouter.invoke(task, messages, schema, budget_ms)`，按 `structured` 能力选 json_schema / json_object + schema 提示 / tool calling，统一 Pydantic 校验，失败带错误重试一次；tag=internal，metadata 含 task / session_id / lane；DeepSeek 走 json_object 实测。
