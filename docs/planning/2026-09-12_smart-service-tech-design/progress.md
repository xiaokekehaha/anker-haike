# 工作记录

## 2026-09-12
- 阅读赛道说明与既有 planning 目录，确认无已有技术设计。
- 完成 WeKnora、LangGraph、Dify、RAGFlow 等调研（网络搜索）。
- 写出前置决策与四步设计文档、技术调研文档。
- 用户要求前端轻量 TypeScript、后端 Python：调研 Preact / Svelte / Lit 与 FastAPI + LangGraph SSE 模式，新增 05_frontend-design.md，更新决策 D6、D9 与总体 / 详细设计。
- 评估 pi 作为 agent 运行时，结论不采用；复核前端轻量方案成立；输出 06_architecture-final.md 最终架构图与 A1 数据流。
- 采纳用户修正：前端改为 Vite + React 19 + TS（Preact 备选），补充 run_started / tool_call / awaiting_input / error.recoverable / done.reason 事件与前端 6 态状态机；修正 Preact 体积、AI SDK 多框架、CopilotKit Python 接入等表述。
- 按用户给出的 Agent 系统设计清单逐项对照，新增 07 文档补齐 16 项，并回填 01/03/04 相关段落。
- 未访问数据库，未修改外部文档。
- 补充 model-selection.md：逐难点梳理业内方案、开源模型、本机可行性、多模态需求，并给出云端 / 本机分环节选型表。本机为 M5 16 GB，未装 Ollama。
- 用户决定不做本机模型部署，全部远程：重写 model-selection.md 第 3 节为 ModelRouter 多厂商适配层设计（海外 / 国内双通道、能力矩阵、分环节路由表、降级规则、models.yaml 示例、bake-off 验证）；同步更新 D7、tech-stack-survey、02/03/04 设计文档。
- 用户确认：默认国内通道；第一版接百炼 Qwen、DeepSeek、智谱 GLM、Claude / Gemini 四家；购买凭证识别纳入演示。model-selection.md 第 4 节改为已确认并给出第一版默认路由表。
- 购买凭证识别纳入范围：更新 D2、01 范围与 F5 / A3 用例、03 模块 1.8 与接口（receipt_card 事件、confirm_receipt_fields 动作）。
- 用户确认：内置 ModelRouter、允许跨通道降级、凭证先确认字段再查规则。更新 D12 / D13、05 前端事件（receipt_card、confirm_receipt）、03 模块 1.8、model-selection 第 4 节。
- 用户确认 D1（扫地机吸力异常）、D4（WeKnora）、D5（LangGraph）。所有决策已定；06_architecture-final.md 模型层改为 ModelRouter 远程多厂商，去除 Ollama。
- 用户确认：模型 ID 先用抽象别名、结构化输出统一由 ModelRouter 适配、bake-off 四项门槛、本轮只完善设计文档。model-selection.md 3.8 补充门槛表与裁决规则，第 4 节记录全部确认项。
- 基于 2026-09-12_smart-service-design-review 的 11 项意见完善设计：新增 08（执行契约）与 09（计划 / 规则 / 知识 / 凭证），修订 00–07 与 model-selection（YAML 冒号修正、Embedding / Rerank 改远程、路由表单一来源、ModelRouter invoke / stream 分离）。未访问数据库，未修改评审目录。
