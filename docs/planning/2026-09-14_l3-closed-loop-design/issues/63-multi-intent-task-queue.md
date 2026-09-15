# 63: 多意图任务队列与自动接续

**What to build:** `reduce_turn` 把 `secondary_intents` 中属于 CONSULT / REMEDY / report_problem 的项写入 `issue.task_queue[{task_id, intent, quote, status, created_input_id}]`（去重）；优先级 safety > request_human > REMEDY > report_problem > CONSULT > social 决定主任务；`reply` 首条可见消息后追加确定性顺序告知句；`close` / `execute` 完成 / `consult` 完成时检查队列 → 同 run 内进入下一任务节点（consult 或 service_context），发 `issue_changed`；用户中途说「先查物流」→ interpret `resume_task`（复用 resume_issue 语义，target=task_id）切换主任务；队列进快照与摘要。

**Blocked by:** 51, 58

**Status:** todo

**Owner:** —

- [ ] A7：「扫地机不吸了，另外上周的换货单发出去了吗」→ 队列 [logistics_query]；顺序告知句；排障 close 后同 run 出物流答案
- [ ] 两个 REMEDY + 一个 CONSULT 的排序单测；重复意图去重
- [ ] 排障等待步骤卡期间用户问物流 → 不打断 pending_card，consult 内联回答后 pending 仍有效
- [ ] `data/eval/routing/cases.yaml` ≥ 20 条多意图样本，主意图 / 次意图 / 顺序准确率报告

**设计依据：** 06 §3；00 D-L3-12
