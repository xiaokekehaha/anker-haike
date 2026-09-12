# 智能服务赛道技术设计

## 目标
基于 docs/smart-service-track.md 的赛道要求，产出四步结构的技术设计文档，并调研可复用的主流开源技术。

## 阶段
1. 技术栈调研（WeKnora、LangGraph、Dify、RAGFlow 等） — complete
2. 记录前置决策（场景、数据假设、选型） — complete
3. 第一步：背景与目标、需求范围、非功能需求 — complete
4. 第二步：总体设计（架构、数据流程、状态机、会话模型） — complete
5. 第三步：详细设计（模块、接口、数据、Prompt） — complete
6. 第四步：稳定性、性能容量、监控告警、灰度回滚 — complete
6b. 前端轻量方案调研与组件设计 — complete
6c. 模型选型与远程多模型适配层设计（含凭证识别范围扩展） — complete
6c. pi 评估、前端复核、最终架构图 — complete
6d. Agent 系统设计清单对照与补齐 — complete
7. 用户评审与修订 — complete（2026-09-12 全部决策确认）
8. 采纳设计评审 R1–R11 并修订全部文档 — complete

## 文件清单
- 00_decisions.md — 前置决策
- 01_background-scope-nfr.md — 第一步
- 02_overall-design.md — 第二步
- 03_detailed-design.md — 第三步
- 04_stability-ops.md — 第四步
- 05_frontend-design.md — 前端组件设计（轻量 TS）
- 06_architecture-final.md — 最终架构 ASCII 图与数据流
- 07_agent-system-design-checklist.md — 四步法对照与补齐（token 估算、缓存、安全、路由等）
- 08_session-execution-contract.md — 会话执行契约：run / interrupt / card / action / snapshot / deadline
- 09_plans-rules-knowledge.md — 规则检查点、产品适用性、有限排障计划、知识四态、凭证核对、回放分离
- tech-stack-survey.md — 主流技术调研
- model-selection.md — 难点分析与模型选型
- findings.md / progress.md — 过程记录

## Next Step
所有前置决策已定（D1–D17），本轮只做设计文档。评审 11 项已全部落入 08 / 09 与各文档修订。剩余集成验证项：IV-1 WeKnora knowledge_ids 过滤参数在锁定镜像后核对。进入实现前：核对各厂商当前模型 ID 写入 models.yaml；准备 bake-off 金标样本并按 model-selection.md 3.8 门槛跑评测；实现阶段另开 planning 任务。
