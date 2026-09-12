# 25: 范围外产品 R8 与 request_human 全局动作

**What to build:** 选中 in_scope=false 的候选 → out_of_scope 子流程：说明本期仅支持扫地机，生成简短摘要 → escalate(R8)。request_human 在任何状态可用：忽略 version 与 pending 校验，若有 active run 先取消再执行 escalate。

**Blocked by:** 16（升级摘要 escalation_summary 与 SummaryCard）、21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** done（2026-09-12 后端；2026-09-13 核对前端按钮已随票 06 集成）

- [x] A2 选吸奶器 → 说明文本 → escalation_summary(reason R8)（out_of_scope 节点发 progress(out_of_scope) + 固定说明文本 → escalate(R8)；摘要 product=eufy S1 Pro 吸奶器；只提到范围外品类无型号时同样 R8，摘要产品写「充电器（型号未确认）」；uvicorn + Postgres 实测）
- [x] streaming 中点「请求人工」→ 当前 run 停止 → 升级摘要（router 在取锁前先 cancel active run，原流 done(cancelled)，新 run 从 START 经 route_entry 直达 human_request → escalate(R3)；实测 0.10 s 返回，快照 cancelled_run 与 stage=escalate）
- [x] awaiting_input 中点「请求人工」不返回 409（忽略 version / pending 校验；有 interrupt 时 Command(resume) 经 apply_action 以 R3 升级并作废卡片，safety_flags 记 source=action；同 action_id 重放 replayed=true）
- [x] 前端「请求人工」按钮在所有状态可见可点（Composer.tsx 常驻「请求人工」按钮，仅离线时禁用；useSession.act 对 request_human 跳过 activeRun / 进行中操作的拦截）

**设计依据：** 09 §2.1；08 §4 步骤 4；02 §3
