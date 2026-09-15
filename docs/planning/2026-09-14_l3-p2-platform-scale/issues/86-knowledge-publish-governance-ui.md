# 86: 知识审核发布治理 UI

**What to build:** 在 P1 70 的 `publish_state` 字段上做管理端流程：知识列表（按库 / 品类 / 区域 / 状态筛选）、条目详情（正文、元数据、引用次数、最近被命中的会话）、状态流转 draft → approved → published → withdrawn（审核人、时间、备注落 `knowledge_audit`）、批量操作、回滚到上一 published 版本；候选知识来源：P1 80 质量闭环沉淀的好方案、71 工单抽取的处置模板；发布触发 manifest 与 kb_ver 更新并写 RELEASE。

**Blocked by:** P1 70, 80

**Status:** todo

**Owner:** —

- [ ] 未 published 条目零召回（复用 70 断言）；状态流转非法边拒绝
- [ ] 审计表记录每次流转；回滚后检索命中旧版本
- [ ] 页面测试 + API 鉴权

**设计依据：** 差距分析 §4.6；agentic-rag-evaluation 发布状态建议
