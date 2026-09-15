# 56: propose 节点、方案模板与 ProposalCard

**What to build:** `propose` 节点：`PolicyDecision.remedies` 中 eligible 项 → 方案 options（确定性模板：标题 / 费用承担 / 条件 / 条款引用 / auto_allowed 标记 / 预计时长来自 actions.yaml），排序 replace > repair > refund；`needs_human` → `await_human`；无 eligible → 「按当前政策无法自动办理」+ 条款 + `summarize`。可选 `propose.wording` 任务（models.yaml 新 task，轻量档）只润色标题与说明句，沿用 `polish.py` 整句保持校验 + 承诺禁词表，失败直渲染。`prepare_proposal → await_input` 发 `proposal_card`；`apply_action(confirm_proposal)` 记 chosen_option_id → `authorize`；`decline_proposal(want_other)` → 重新 propose 排除该项；`(request_human)` → summarize；`(not_now)` → commit_issue。承诺账本：每个展示的 option 落 `case.commitments`（票 59 表落地前先存 state）。

**Blocked by:** 51, 54, 55

**Status:** todo

**Owner:** —

- [ ] A5：两项方案（换货 / 维修）带各自条款；卡片文案中不出现禁词（字符串断言）
- [ ] A6：needs_human → 用户可见诚实说明含条款 → 进入 await_human 路径（票 60 前先到 summarize）
- [ ] 润色失败 / 超预算直渲染，`model_trace` 标 skipped
- [ ] 前端 `ProposalCard.tsx`：选项、条款展开、确认 / 换一个 / 转人工三按钮；快照恢复 chosen_option_id

**设计依据：** 02 §2.1、§3；04 §5；06 §5
