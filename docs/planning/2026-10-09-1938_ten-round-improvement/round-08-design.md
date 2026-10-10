# 第 8 轮：结束结果与人工状态使用事实

## 问题 → 证据

T29 在第六轮真实完成三项操作后，因过保成为 closed_unresolved。服务回复已经如实说明，但 analytics/l3.py 把这个状态和仅生成摘要都映射为 escalated_human，统计事实与实际队列不一致。derive.classify 没有识别 closed_unresolved，可能被先前 consult_answered 或 closing 消息覆盖。

T58 第五轮仍出现“live hand-over isn't connected yet”。这是固定模板，无论实际服务是否具备人工审核队列都会这样说，属于系统能力文案错误，不能归因于官方场景。

## 方案

结案、已整理摘要、已排人工审核、真人已处理分别依据案件状态和人工事件。新增 closed_unresolved 统计结果，优先于咨询已答和结束语；计入终结分母，不计自行解决。已有 escalated 保持“摘要已整理、需后续处理”的含义，去掉 L3 将其改名为 escalated_human 的错误映射。实时 SQL 与保留期快照共用投影一并修正。human_involved 仅来自真实人工决定/事件，案件状态本身不能证明真人已处理。

客户模板只描述当前记录：已整理但未提交、已提交等待审核、已有审核记录。投诉分支可提供整理和提交请求的入口，不声称实时连接状态，也不承诺已经接单。人工边界仍以实际案件记录为准。

## 需求与验收

| ID | 需求 | 验收 |
| --- | --- | --- |
| R9a | 关闭未解决优先 | 即使有 consult_answered、closing 或摘要，仍为 closed_unresolved；有终结时间 |
| R9b | 三处投影一致 | classify、episode、METRIC_ROWS_SQL 对 closed_unresolved/escalated_summary/awaiting_approval/closed 一致；真实 SQL 集成验证 |
| R9c | 指标与展示 | 关闭未解决进入终结分母、不进入 managed；旧会话解决比例分母包含它；管理端有明确标签 |
| R2.1 | 文案不虚构能力 | 无案例/仅摘要/已排队/已有人工记录均明确区分；不出现“未接入”的全局断言 |

已有历史行不在本轮自动改写；有案件关联的实时与保留期 SQL 自动采用当前真实案件状态。无原始记录的旧错误标签不能凭空重判，报告中说明。无数据库结构迁移，不改变审批或业务执行逻辑。
