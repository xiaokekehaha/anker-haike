# 定位事实

- 当前 HEAD 为 bf29496，但 interpret/reduce/l3_intents 及其测试已有并行修改。后续证据分别标注历史首测、当前代码或离线注入复现。
- 原始轨迹在 ../2026-10-09-1515_full-official-evaluation/T*.json；journey.runs 包含 nodes、retrieval_calls、model_calls。
- T30 首测记录 knowledge_status=ok，检索完成后进入 R5；是否为召回、裁剪或筛选问题需要进一步核对，不能仅凭终点归因。
- 暂未发现 CONTEXT.md 或 ADR 文件；参考现有设计与测评记录。

## 已验证根因

- T18/T22/T34：日志中的语义输出有症状候选；引用分别出现省略拼接、倒序拼接、拼写/大小写改写。`quoted()` 均返回 false，patches/facts/symptoms 为空。查询回退原文，但 synthesize 的有效症状仍为空，确定性拒绝正确候选。
- T34 的目标文档 rv-0312 对应第三个可见候选 `35e6b0fb-63af-48c5-aa62-839ede4e16cb`；第一个候选对应 rv-0389，不能混淆。
- T30：无效知识引用逐项等于用户事实 fact_id；更正为本轮合法知识引用后，原函数保留正确方案。
- T31：operation_changed 在首次求助直接路由 reassess。固定基线的最小状态与单变量对照已复现。
- 恢复流程只重看首次被预算排除的候选，无法修复空事实和引用错误；无方案最终被合并到 R5。
- T52/T61 原句在事实和 query 中保留，问题出在适用性判断和追问前提；最佳文档召回情况尚未单独验收。
- T13 是当前官方错误码索引缺少 5116 的对照，不能用相近码代替。

完整证据、修改位置及边界见 root-cause.md；原始状态见 checkpoint-evidence.json，事实抽取语义见 intake-evidence.json，离线对照见 reproduction-results.json。
