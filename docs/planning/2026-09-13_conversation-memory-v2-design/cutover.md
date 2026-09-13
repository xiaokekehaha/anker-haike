# 历史清理与统一切换

依据：用户明确“历史可以清理，不用考虑兼容”。本页规定实施时的范围与顺序，本轮仅完成设计，没有执行删除。

## 1. 简化后的方案

直接改造现有 graph.py 和当前 HTTP/SSE/快照契约，前后端统一发布。省去旧格式 HistoryReader、双图、双解码器、版本协商 Header、session_protocols 表、按会话固定引擎、活动 checkpoint 迁移和新旧会话灰度分流。

清理发布前的历史会话后，新会话全部使用新结构。新版本自身的问答历史、断流续接、消息幂等、进程重启恢复及同会话问题切换照常实现；“不考虑兼容”不意味着取消这些运行能力。

## 2. 数据范围

实施时先冻结待清理 session_id 集合：来自 sessions、session_events、session_actions、session_images、若已存在的 session_inputs/conversation_summaries 与本项目会话 checkpoint/analytics 的并集，识别无 sessions 投影的孤儿会话。表是否存在先查 schema；导出各表匹配数量供清理前后核对，不把清理扩展为整库重建。

| 类别 | 操作 |
| --- | --- |
| sessions、session_events、session_actions、session_images | 清理冻结集合对应的历史会话行及其图片文件/对象（如存在外置存储）。 |
| checkpoints、checkpoint_blobs、checkpoint_writes | 以对应 thread_id 清理本项目会话状态；不清理 checkpoint schema/migrations 元数据。 |
| analytics.session_facts、run_facts、node_runs、model_calls、retrieval_calls、cases | 按 session_id 清理关联历史派生记录；session_id 为空的探活/独立评测记录不算会话历史。 |
| session_inputs、conversation_summaries | 若部署环境已有测试版，清理同集合的输入账本/派生摘要；新建表按结构迁移创建。 |
| 应用内 run、缓存、后台摘要/分析任务 | 停止并清空与旧会话关联的运行状态，防止后台任务写回。 |
| 浏览器 sessionStorage:haike.session_id 与 localStorage:haike.recent_sessions | 新前端遇 not_found 清除当前无效引用与对应最近列表项并允许新建；不伪造历史迁移。 |
| 产品目录、故障卡、预写计划、质保参考/经销商资料、模型与规则配置 | 保留，不属于历史会话。 |
| WeKnora 知识库及其他数据库 | 不因本次切换删除或重置。 |
| 原诊断文档、脱敏验收样本、历史日志 | 可保留作诊断证据，不作为新运行历史来源；禁止后台回填旧会话。现有日志保留策略不变。 |

当前 retention.py 的 SESSION_TABLES 只列核心会话/checkpoint 表，没有包含所有 analytics 派生表。实施需扩充按会话清理覆盖，不能只调用现有清理函数就宣称完成。清理范围从 schema 与外键实际核对，不能依靠硬编码的表名前缀批量删库。

## 3. 实施顺序

1. 在测试环境完成新契约、业务、恢复与语义验收，准备同一版本的前端构建与后端。
2. 进入短维护窗口，拒绝新消息/动作，停止后台写入；等待或取消已有 active run 并完成资源收尾。
3. 冻结历史会话集合与计数，执行按集合关联清理；核对孤儿、附件、analytics、缓存均无可恢复的旧会话数据。
4. 运行本项目 Alembic 结构迁移，同步部署前后端；清除旧应用进程中的 run/checkpointer 缓存。
5. 先内网冒烟：创建会话→历史问答→待卡片解释→反馈→纠正→新问题→刷新/续接；验证新协议一致。
6. 旧浏览器引用收到 not_found 后能正常进入新会话；核心非会话数据数量与版本保持一致。
7. 验证后恢复入口，记录清理结果、部署版本和冒烟结果。失败保持入口关闭，修复后重试，不实现旧历史格式恢复。

不使用 `make reset`、Compose 删除数据卷或整库 DROP 作为历史清理办法。新结构的数据库 schema 由迁移版本管理；本方案不需要业务历史转换脚本。

迁移明确包含：新增账本/摘要表、事件 event_id 唯一约束与 visibility、sessions 发布 checkpoint 指针与显式 version、会话 timezone；旧 session_actions 清理后删除，运行时统一使用 session_inputs。首期单 RunManager worker，启动发布对账/未完成输出恢复完成后才开放输入；不得将当前进程看不到 handle 的其他活动进程任务一律当孤儿结束。

## 4. 切换验收

- 清理集合在会话、checkpoint、analytics、附件关联中均无残留，后台任务不会复活旧会话。
- 产品目录、知识库、故障计划、配置、质保参考资料未被清理。
- 所有新创建会话使用同一新契约，无旧格式回退或按会话分流。
- not_found 处理、新会话冒烟、消息重试和断流恢复通过。
- 会话默认 TTL 保持现有配置，历史清理只是此次升级动作，不改成每次启动都清空。
