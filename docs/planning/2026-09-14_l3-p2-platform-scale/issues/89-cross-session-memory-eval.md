# 89: 跨会话用户级记忆评估

**What to build:** 评估而非上线：在可信身份关联（登录 / 手机号脱敏哈希）前提下，用户级记忆的最小形态——已确认设备清单、历史案件摘要、偏好（detail_level / language）、复发标记；候选实现：项目 DB 表（`user_profiles` + 引用 cases）vs Mem0 类外部记忆；隐私与保留（用户删除即级联；与 retention 一致）；对托管率 / 复发处理效率的预期收益；给出是否实施与实施形态的结论报告。

**Blocked by:** P1 80（episode / 复发口径）；身份关联方案确认

**Status:** todo

**Owner:** —

- [ ] 报告含数据模型草案、隐私影响、与会话记忆 V2 的边界（不重复存事实）
- [ ] 若实施：先做「同一用户回访时主动带出未结案件」一个场景的原型

**设计依据：** conversation-memory-v2 设计（Mem0 deferred）；05 §2 重开
