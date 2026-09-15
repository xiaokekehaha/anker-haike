# 60: 最小人工协同回路（审批 API、队列 / 详情页、human_decision 恢复）

**What to build:** admin API：`GET /admin/api/cases/queue`、`GET /admin/api/cases/{id}`、`POST /admin/api/cases/{id}/decision`（approve / reject / request_info，含 edited_option、override_reason 必填当覆盖政策）、`/close`、`/reopen`；乐观版本 409；actor 取 basic auth 用户。`sessions/inputs.py` 新输入 kind `human_decision`（entry=human_decision，payload decision_id），`route_entry → apply_human_decision`：approve → 覆盖 chosen_option（source=human）→ authorize（政策项按人工批准视为通过，其余检查照常）→ execute；reject → propose 排除项或 summarize，用户可见含人工备注；request_info → dialogue 提问，案件回 awaiting_confirmation。`await_human` 节点：case → awaiting_approval，用户可见「等待人工审核」。前端管理端 `Approvals.tsx`、`CaseDetail.tsx`（复用 ReadonlyTimeline、ProposalCard 加编辑、政策条件表、门检查表、决策面板）；Dashboard 待审批 / 平均等待 / complaint_risk 卡。

**Blocked by:** 57, 59

**Status:** in-progress

**Owner:** —

- [ ] A6 全链：gate fail → 队列可见（complaint_risk 置顶）→ approve → 会话自动 run → execution_card；用户端 CaseStatus 从等待到办理中
- [ ] reject → 用户收到解释 + 备选方案 / 交接摘要；request_info → 用户回答后回到 proposing
- [ ] 两管理员并发决定 → 一个 409；同 decision_id 重投递幂等
- [ ] 人工覆盖政策必须填 override_reason，落 human_decisions 并出现在摘要

**设计依据：** 05 §4；02 §2.1–2.2；00 D-L3-8

人工结案 / 重开、会话同步和前端入口已补齐，见 [17_manual-case-lifecycle.md](../17_manual-case-lifecycle.md)。审批主链已有实现与定向证据；整票验收仍以当前版本 A6 和上述清单为准。
