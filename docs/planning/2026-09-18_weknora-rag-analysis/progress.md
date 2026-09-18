# 进度

- 2026-09-18：读取项目约定、research 与 planning-with-files 技能；初始 git 工作区干净。
- 已确认部署定义包含 WeKnora app/UI、DocReader、Postgres/pgvector/pg_search、Redis。
- 固定版本源码位于 /tmp/haike-weknora-v080-20260918，镜像revision与tag一致。
- 根据 research 技能并行委派两个只读子任务：上游入库/检索、聊天pipeline。各自仅写独立证据文档。
- 完成指定会话、知识库配置、数据计数和单request日志读取，未新发起模型调用。
- 完成analysis.md、case-evidence.md和两份上游源码分析；补充addendum.md记录复核结论。
- 核对123个本地/固定commit源码链接、源码行号范围与Markdown代码块，全部通过。仅新增本任务文档；未改业务实现，未提交Git。
- 未运行业务测试：本次只有研究文档与只读运行检查。临时SQL和Python脚本完成后删除。
- 用户继续要求评估链路B如何借鉴链路A，聚焦改写、查找、召回、排序及修改必要性；当前范围为分析方案，不直接改业务代码或启用真实模型开关。
- 并行核对历史评测与运行编排，主分析核对query/adapter/search/rerank的候选数据流。
- 完成chain-b-recommendations.md、chain-b-runtime.md、chain-b-evaluation.md：按必要性区分候选保留、充分性补查、两轮上下文选择与可选模型增强。
- 核对3份链路B文档的105个本地链接、行号范围与代码围栏，通过。记录运行图与评测入口差异、统一context层和旧评测口径勘误。
- 本轮仍仅改本任务研究文档；未修改业务代码或开关、未调用模型、未运行业务测试、未提交Git。
