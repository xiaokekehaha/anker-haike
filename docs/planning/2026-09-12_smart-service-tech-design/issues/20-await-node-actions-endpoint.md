# 20: 三段式等待节点与 /actions 基本通路

**What to build:** 实现通用的 prepare_card → await_input(interrupt) → apply_action 三段式节点；card_id 由业务位置派生（uuid5），await_input 发卡片事件与 awaiting_input 后 interrupt，run 以 done(awaiting_input) 结束。POST /actions 以 Command(resume) 恢复并开新 SSE 流。

**Blocked by:** 18（安抚句流式先出与 <data> 包裹）、19（产品目录表与匹配服务）

**Status:** ready-for-agent

- [ ] prepare_card 只执行一次（用计数器断言），await_input 重跑时重发同一 card_id
- [ ] awaiting_input 与 done(awaiting_input) 成对出现且 version 一致
- [ ] /actions 恢复后新 run 的 run_started.resumed=true
- [ ] pending_card 写入图状态并出现在快照 pending_input

**设计依据：** 08 §3、§4
