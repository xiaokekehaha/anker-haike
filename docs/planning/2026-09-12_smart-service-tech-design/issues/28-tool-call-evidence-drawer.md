# 28: tool_call 与 evidence 事件 + EvidenceDrawer

**What to build:** 检索调用发 tool_call(started / finished / failed) 与 evidence 事件（evidence_id 稳定），前端显示工具行并在 EvidenceDrawer 折叠列出来源片段；前端进入 tool_running 态。先用文本 query 检索打通，不依赖读图。

**Blocked by:** 27（KnowledgeAdapter：scope → knowledge_ids 与四态结果）

**Status:** ready-for-agent

- [ ] A1 话术下时间线出现「检索知识库」工具行与来源列表
- [ ] evidence_id 在同一会话内稳定，可被后续 step.evidence_ids 引用
- [ ] tool_call(failed) 时前端显示失败但流程继续
- [ ] no_match / unavailable 在前端有对应文字标记

**设计依据：** 08 §5；05 §3、§4；09 §4
