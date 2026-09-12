# 25: 范围外产品 R8 与 request_human 全局动作

**What to build:** 选中 in_scope=false 的候选 → out_of_scope 子流程：说明本期仅支持扫地机，生成简短摘要 → escalate(R8)。request_human 在任何状态可用：忽略 version 与 pending 校验，若有 active run 先取消再执行 escalate。

**Blocked by:** 16（升级摘要 escalation_summary 与 SummaryCard）、21（产品确认卡片 ProductCard 端到端（A2 前半））

**Status:** ready-for-agent

- [ ] A2 选吸奶器 → 说明文本 → escalation_summary(reason R8)
- [ ] streaming 中点「请求人工」→ 当前 run 停止 → 升级摘要
- [ ] awaiting_input 中点「请求人工」不返回 409
- [ ] 前端「请求人工」按钮在所有状态可见可点

**设计依据：** 09 §2.1；08 §4 步骤 4；02 §3
