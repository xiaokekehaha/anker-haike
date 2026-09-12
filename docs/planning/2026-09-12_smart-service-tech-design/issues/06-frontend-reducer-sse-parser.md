# 06: 前端 reducer、SSE 解析与 ProgressBar

**What to build:** 前端用 fetch + ReadableStream 手写 SSE 解析，reducer 处理 run_started / progress / ping / done，驱动 idle ↔ streaming 两态，ProgressBar 随 progress 事件推进。用户发出一条消息后能看到阶段条动起来并回到可输入状态。

**Blocked by:** 04（前端 TS 类型生成、CI 比对与 fixtures 骨架）、05（会话创建与 SSE 基础流）

**Status:** done（2026-09-12，含前端集成：App 接线与全部卡片组件）

**Owner:** Claude Code B（2026-09-12 认领；Codex 已停。与前端集成一并做：reducer / SSE / useSession / 卡片组件 / App 接线，覆盖票 06、08 前端、13/14/16/21/28/29 的前端部分）

- [x] reducer 为纯函数，对 fixtures 中的事件序列有单元测试（`frontend/src/state/reducer.ts`；`reducer.test.ts` 用 `contracts/fixtures/events.valid.json` 15 种事件跑通，另测消息聚合 / 替换、tool_running、awaiting_input、error→failed、restore）
- [x] Composer 发送文本后进入 streaming，done 后回到 idle（`useSession.send`：创建会话 → 多部分 /messages → readSSE；App 集成测试 mock fetch 验证气泡、工具行、阶段条与 ui 回到 idle）
- [x] ProgressBar 五阶段切换带 300 ms 过渡（沿用票 02 的 ProgressBar，`stage` 改为来自 reducer；CSS transition .3s 已有）
- [x] 15 s 无事件时显示「仍在处理」提示（useSession 每秒检查 lastEventAt，>15 s 置 stalled，App 显示「仍在处理，请稍候…」；超过 deadline + 5 s 中止流并走 recovering → 快照 → 续接 events?after_seq）
- [x] session_id 存 sessionStorage（key `haike.session_id`；加载时先读快照 restore，active_run 未过期则续接）

**设计依据：** 05 §4–§6

**实现记录（2026-09-12，Claude Code B，Codex 停后接手前端集成）：** `src/state/{types,reducer,useSession}.ts`、`src/api/{sse,client}.ts`；组件 AssistantBubble（react-markdown + rehype-sanitize，脚本标签剥离，fallback 标「简化回复」）、ToolRow、EvidenceDrawer（与 StepCard hover 联动高亮）、ProductCard（in_scope=false 标「本期不支持」，选后 disabled）、StepCard（旧卡折叠一行）、ReceiptCard（confidence < 0.7 标黄）、SummaryCard（一键复制，与后端 summary_to_text 同款）、Toast、Timeline；App 去掉 CHAT_OFFLINE，Composer 接 onSend / 请求人工 / 取消；动作带 action_id / expected_version / interrupt_id / card_id，409 用附带快照重建。前端 71 项测试、typecheck、build 通过（bundle 568 kB，主要来自 react-markdown，后续可 code-split）。覆盖的其他票前端部分：08（recovering / 续接）、13/14（气泡 / 替换 / 标注）、16（SummaryCard）、21（ProductCard）、28（工具行 / EvidenceDrawer）、29（Composer 选图 / UserBubble）。StepCard / ReceiptCard 组件就位，等票 34 / 40 后端下发事件。
