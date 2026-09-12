# 16: 升级摘要 escalation_summary 与 SummaryCard

**What to build:** escalate 的 summarize 节点不依赖模型即可生成结构化摘要（产品、问题、观察、假设、步骤、原因、情绪、凭证状态 not_collected、model_trace），发 escalation_summary 事件；前端 SummaryCard 渲染并一键复制。先以 R4 安全升级路径打通。

**Blocked by:** 06（前端 reducer、SSE 解析与 ProgressBar）、15（规则服务骨架与 CP-in 安全升级）

**Status:** ready-for-agent

- [ ] 用户首句触发安全词 → 安抚 → escalation_summary → done(completed) 全链路可演示
- [ ] summary 对象层级与契约一致，receipt.status=not_collected
- [ ] SummaryCard 复制内容为可读文本，含全部五要素
- [ ] 模型不可用时摘要仍能生成，model_trace 标 summary_polish=skipped

**设计依据：** 08 §5；09 §4、§5.1
