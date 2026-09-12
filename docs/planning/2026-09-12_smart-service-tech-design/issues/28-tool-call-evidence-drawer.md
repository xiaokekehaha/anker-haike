# 28: tool_call 与 evidence 事件 + EvidenceDrawer

**What to build:** 检索调用发 tool_call(started / finished / failed) 与 evidence 事件（evidence_id 稳定），前端显示工具行并在 EvidenceDrawer 折叠列出来源片段；前端进入 tool_running 态。先用文本 query 检索打通，不依赖读图。

**Blocked by:** 27（KnowledgeAdapter：scope → knowledge_ids 与四态结果）

**Status:** done（2026-09-12；EvidenceDrawer / ToolRow / tool_running 随前端集成完成，见票 06）

**Owner:** 后端 Claude Code B（graph.py `retrieve` 节点、`app/knowledge/runtime.py`）；前端建议 Codex 认领（EvidenceDrawer、工具行、tool_running 态）

- [x] A1 话术下时间线出现「检索知识库」工具行与来源列表（后端：确认产品 / 品类后进入 `retrieve` 节点，发 progress(diagnose, retrieve) → tool_call started → finished → evidence；快照 timeline 折叠出 kind=tool 与 kind=evidence。真实端到端：X9 Pro 话术命中 10 条，全部在 manual_rv_v1 / 排障手册 / X9 Pro 工单范围内。前端渲染待 Codex）
- [x] evidence_id 在同一会话内稳定，可被后续 step.evidence_ids 引用（evidence_id = WeKnora chunk id；状态 `evidence` 按 id 累积去重；两轮消息返回同一 id 的测试）
- [x] tool_call(failed) 时前端显示失败但流程继续（后端：adapter 缺失或两库均 unavailable → tool_call failed「知识库暂不可用，按标准排障流程」，run 仍以 done(completed) 结束并进入 diagnose；前端展示待 Codex）
- [x] no_match / unavailable 在前端有对应文字标记（后端已在 tool_call.summary 给出固定文案：「未找到匹配知识，按标准排障流程」/「知识库暂不可用，按标准排障流程」，状态写入 `knowledge_status`；前端按 summary 直接显示即可）

**设计依据：** 08 §5；05 §3、§4；09 §4

**实现记录（2026-09-12，Claude Code B）：** graph.py 新增 `retrieve` 节点（query = 抽取到的症状拼接，退回原文；scope 由 product_state / product_confirmed 派生；同时查 kb_manual 与 kb_tickets，每库 top 5；反证工单已由适配器排后）、`_after_product()` 路由：confirmed_sku / category_only → retrieve，unknown → 不检索（票 24 追问）；`app/knowledge/runtime.py` 进程级适配器（需 WEKNORA_API_KEY + data/knowledge/manifest.json，索引首次使用时拉取；`HAIKE_KNOWLEDGE=off` 单测默认关闭）。tests/test_retrieve_events.py 6 项。**对 A 的影响：** `tests/test_sessions_actions.py::test_select_product_resumes_run_and_completes` 的精确事件列表改为忽略 tool_call 后比对主干（已改，全量 207 通过）。

**给前端（Codex）的接口说明：** tool_call 事件 `{tool_id, name: knowledge.search, status: started|finished|failed, summary}`，同一 tool_id 先 started 后 finished/failed；evidence 事件 `{items: [{evidence_id, source: kb_manual|kb_tickets, doc_id, doc_version, chunk_id, snippet, score, status}]}`；快照 timeline 项 kind=tool / kind=evidence。tool_running 态 = 收到 started 且未收到同 tool_id 的 finished/failed。
