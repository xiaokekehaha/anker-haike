# 升级后会话记忆与后续消息策略

## Goal
修复"一次升级后整条会话被冻结"的状态机缺陷：升级原因改为 run 级瞬态、会话级只保留升级历史；
升级后的新消息进入显式的 followup 策略节点（补充 / 元问题 / 纠正 / 新话题 / 再要人工 / 寒暄），
模型看到带时间戳的历史窗口；转人工摘要的观察项由带时间的结构化记录生成，不再机械拼接原文。
不引入 mem0 等外部长期记忆（无用户身份锚点、会话 24h TTL，见 findings.md）。

## Phases
1. 后端：状态分层 + followup 节点 + 摘要观察项结构化 + analytics 兼容 + 回归测试。**Status:** complete
2. 前端：摘要卡"已更新 HH:MM"角标；观测台 journey 展示 followup 意图。**Status:** pending
3. 观测：analytics derive 标记"同会话重复升级 / 模型调用零影响"异常。**Status:** pending

## Design（阶段 1）
- `escalate_reason` 保持字段名不变但语义改为"本 run 触发的升级"，runner 在 message / action 入口显式置 None；
  `summarize` 同时写会话级 `last_escalation = {reason, run_id, at, terms}`。
  凭证子流程（pending_card.kind == upload_receipt）在 intake 里用 `last_escalation.reason` 回填，行为不变。
- `route_entry`：entry == message 且 stage == escalate 且无 pending_card → `followup`。
  其余（等凭证、等确认卡）保持进 intake，避免扩大改动面。
- `followup` 节点：记录消息 → CP-in（R4 新命中且与上次原因不同 → 走 escalate，安全文案只发一次）→
  规则优先分类（新话题 / 再要人工 / 元问题 / 纠正 / 寒暄），规则不命中且有模型时用 intake 链 +
  带时间戳的最近 8 轮历史做一次结构化抽取（意图 + 产品线索 + 症状）→ 按意图动作：
  - new_topic：归档当前 topic（product / symptoms / last_escalation / messages 区间）到 `topics`，重置槽位，
    stage 回 intake；消息里带事实则直接交 intake 继续，否则回一句引导。
  - meta_history：不调模型，直接用 messages + 槽位渲染带时间的回顾。
  - correction：有新事实 → 作为"纠正"观察项写入并重发摘要卡；没有 → 追问改哪一项。
  - request_human：一句"已在转接中"，不重发卡片。
  - supplement / image：写入带时间的观察项，重发同 card_id 的摘要卡（前端原地更新），回一句"已补充"。
  - chitchat：一句收尾语。
- `build_summary`：`_user_texts` 只取当前 topic 且不晚于升级 run 的用户消息；观察项 = 结构化 `observations`
  （followup 写入时带 `HH:MM` 前缀）。R3 / R4 仍跳过 polish。
- `analytics/derive.py`：outcome_reason 取 `escalate_reason or last_escalation.reason`。

## Decisions
- 不新增 Stage 字面量，followup 的 progress 事件用 stage=escalate + substage=`followup:<intent>`，契约不变。
- 意图分类复用 `intake` 任务链（不新增 KNOWN_TASKS，避免三条通道配置改动）；model_trace 里 task 记为 `intake.followup`。
- 时间显示用 Asia/Shanghai（环境变量 SUMMARY_TZ 可覆盖），只用于用户可见文本与摘要，状态里仍存 UTC ISO。
- 摘要卡 card_id 保持 `session:reason` 稳定，让前端 upsert 原地更新；"已更新"提示放阶段 2。

## Next Step
阶段 2：前端 SummaryCard 角标；阶段 3：analytics 异常指标。

## Errors Encountered
（见 progress.md）
