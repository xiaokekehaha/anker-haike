# 数据还原与根因（会话 49e8168c9175456092550d1ca3af37f6，2026-09-13）

来源：sessions / session_events / session_actions / session_images 四表、GET /sessions/{id} 快照、编排结构化日志（model_call / state_transition / rule_hit）。

| 时间(UTC) | 用户输入 | 路径 | 模型 | 结果 |
|---|---|---|---|---|
| 05:25:23 | 我的耳机没有声音 | intake → disambiguate → out_of_scope → R8 | qwen 1.8s：耳机 / 没有声音 | 合理 |
| 05:25:46 | 我机器人，冒烟了 | CP-in R4「冒烟」→ escalate（短路，未抽取） | 无 | 产品纠正"机器人"丢失 |
| 05:33:34 | 我之前问了什么问题 | intake → 抽取为空 → 残留 R4 再 escalate | qwen 1.3s，作废 | 重发安全文案 |
| 05:46:40 | 有什么故障 + fault 图 1 张 | 同上 | qwen 2.2s，作废；图未分析 | 重发 |
| 05:49:26 | 新问题 | 同上 | qwen 1.3s，作废 | 重发 |
| 05:49:38 | 动作 request_human | human_request → R3 | 无 | 摘要卡（命中词渲染为枚举名） |
| 05:49:41 | 刚说错了 | intake → 残留 R3 再 escalate | qwen 1.0s，作废 | 重发 R3 文案 |

根因：
1. `escalate_reason` 从不清零，`route_after_intake` 只判有值 → 第一次升级后每轮必进 summarize。
2. stage=escalate 是吸收态，`route_entry` 对它没有分流。
3. CP-in 命中即 return，安全路径不抽取产品线索。
4. 摘要观察项 = messages[1:] 原文加"用户补充"前缀，R3/R4 跳过 polish。
5. 摘要卡 card_id = session:reason，前端按 card_id upsert → 后轮内容覆盖到前轮位置。
6. 4 次作废的 intake 调用合计约 5.8s，观测台看不出"输出被丢弃"。

为什么不上 mem0：sessions 无 user_id、24h TTL、问题在路由与提示词组装而非存储；规则优先 + 25s deadline 的架构下，
多一次 LLM 抽取 + 向量召回既慢又不可确定重放。等有客户身份与跨会话需求再评估。
