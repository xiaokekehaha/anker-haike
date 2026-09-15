# 59: 案件对象：表、状态机、case_changed 与 CaseStatus

**What to build:** 迁移 0006：`cases`、`case_events`、`human_decisions`、`satisfaction_ratings`；`app/cases/service.py`：`open / transition / attach_execution / close / reopen`，非法迁移抛错，每次迁移写 case_events 并发 `case_changed`；`complaint_risk / priority` 字段；结案条件（外部终态 + 用户确认 / 人工结案）；重开触发（同 issue 再报问题 / not_solved / 否认已解决）；快照 `CaseStatusItem`；前端 `CaseStatus.tsx`。analytics `sessions` 投影加 `case_id / case_status / human_involved`。retention：cases 按关闭后 N 天清理；会话删除级联去标识化。

**Blocked by:** 51

**Status:** in-progress

**Owner:** —

- [ ] 状态机单测覆盖全部合法边与 ≥ 5 条非法边；reopen 计数递增
- [ ] `case_changed` 事件与快照一致；刷新后 CaseStatus 恢复
- [ ] 纯排障 resolved 的 issue 不建案件；进入 service_context 即建
- [ ] 删除会话后 cases 保留统计字段、去除原文；retention 单测

**设计依据：** 05 §1–§3、§5；00 D-L3-7
