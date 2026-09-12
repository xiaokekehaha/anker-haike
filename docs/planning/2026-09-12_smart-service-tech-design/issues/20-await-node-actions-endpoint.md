# 20: 三段式等待节点与 /actions 基本通路

**What to build:** 实现通用的 prepare_card → await_input(interrupt) → apply_action 三段式节点；card_id 由业务位置派生（uuid5），await_input 发卡片事件与 awaiting_input 后 interrupt，run 以 done(awaiting_input) 结束。POST /actions 以 Command(resume) 恢复并开新 SSE 流。

**Blocked by:** 18（安抚句流式先出与 <data> 包裹）、19（产品目录表与匹配服务）

**Status:** done（2026-09-12；差异：未等票 18，卡片前暂无安抚句，见下）

- [x] prepare_card 只执行一次（用计数器断言），await_input 重跑时重发同一 card_id（状态 prepare_card_calls 在恢复后仍为 1；恢复 run 重发 product_card 同 card_id，快照按 card_id 折叠成一张）
- [x] awaiting_input 与 done(awaiting_input) 成对出现且 version 一致（version 由节点内 langgraph_step 随中断载荷带出；真实 AsyncPostgresSaver 回归测试覆盖）
- [x] /actions 恢复后新 run 的 run_started.resumed=true（Command(resume=action)；uvicorn 实测 resumed=True、seq 接续）
- [x] pending_card 写入图状态并出现在快照 pending_input（状态 pending_card 与快照 pending_input 的 card_id / version 一致；apply_action 后清空）

**设计依据：** 08 §3、§4

**实现记录（2026-09-12，Claude Code A）：** `app/sessions/cards.py`（uuid5 card_id、节点内 version、目录单例）；graph.py 新增 disambiguate → prepare_card → await_input → apply_action 链，intake 之后先消歧（多命中出卡；单命中直接 confirmed_sku；零命中 unknown 交票 24；选中 in_scope=false 或单命中范围外走 escalate，摘要交票 25）；runner 支持 `resume=`（Command）、识别 `__interrupt__` 发 awaiting_input 并以 done(awaiting_input) 收尾；`POST /sessions/{id}/actions` 用 haike_contracts 校验，基本 409：run_active / not_allowed_now / stale_card / version_mismatch（附快照）。测试 tests/test_sessions_actions.py 7 项 + pg 回归 1 项；后端合计 180 项。

**与票面 / 设计的差异：** 票面 Blocked by 18（安抚句先出），本票未等 18：目前卡片前没有安抚句，18 接入时在 disambiguate 之前插入 reply.stream 即可，三段式机制不受影响。awaiting_input 事件改由运行器在真正中断时发出（节点只发卡片事件），避免恢复重跑时重复发 awaiting_input 误导前端。动作幂等（action_id 去重、会话锁）在票 22，完整 409 语义（含 request_human 例外）在票 23 / 25。
