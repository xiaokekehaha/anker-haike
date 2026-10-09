# 初始证据

- 用户报告 T52 仍将盒子自身充不进电排为盒子给泵充电。
- 18:39 全量复测目录的 progress.md 明确记录 T52 首轮仍进入泵与盒子接触排查；同时另一个会话重建服务，第二轮独立采证中。
- 先前根因报告指出原句和 query 保留了 charging case will not charge；本轮需核实修复后为何仍误选。
- 共享工作区已有其他会话的大量应用和评测改动，本轮仅新建本目录文档。
- 未发现 CONTEXT.md 或诊断区域 ADR。

## 已复现信号

- 执行 jq -e 检查首卡为事实问句或不属于 qa_bp_0067 / qa_bp_0039，18:43 T52 返回 false，exit 1。
- 输入原文包含「My charging case will not charge therefore I cannot charge my pump motors」；检索 query=charging case will not charge，首卡 qa_bp_0067 要求对齐 pump hub 与盒内磁吸端口。
- 第一轮、第二轮及当前工作区 synthesize.py SHA256 相同：7dd49807dca1a5c590165ed811afafffe8e68718b2883ffae2c4b1b90aaf7f83。
- 第二轮 18:47 T52 停在 clarify，但显示「Is the problem with the pump motors itself ...」，问到了泵，而不是先问盒子自身输入供电。

## 待验证假设

1. 模型生成 matched_subject=charging case 或留空，当前服务端不阻断；把它单独改为 pump hub 应触发阻断。
2. 当前结构只比部件名称，未表达电源→盒子 / 盒子→泵关系；同主语或包含短语应被放过。
3. 现有回归测试手工提供 pump in the case，未覆盖误标主语；甚至有同方案 matched_subject=charging case 被保留的正例。

## 尚未读取

- 最新运行的结构化 facts、retrieval_trace、模型原始假设。公开 journey 只记录调用元信息，需要读取会话 checkpoint 和语义事件。

## 最终验证

- 已只读获取两轮 checkpoint，以及对应 intake / diagnose.synthesize 的脱敏模型输出。
- 第一轮实际 matched_subject=charging case、applicability=supported；服务端保留 qa_bp_0067 / qa_bp_0039。
- 原始输出通过当前真实 filter；只改 matched_subject 为 pump hub 或 pump in the case 即被拦。空值、包含 charging case 的短语、恢复完整症状仍放行。
- 第二轮 qa_bp_0039 触发 pump motors 对 charging case 的部件冲突，通用模板精确复现「pump motors itself」问句。两轮 synthesize.py 相同，其他代码不同，不声称全应用重复实验。
- 3 个相关现有测试全部通过；其中第97行测试明确认可 qa_bp_0067 在 charging case 主语下通过，包含真实错误路径。
- 原句及 query 保留盒子问题；query rewrite disabled。直接根因为动作关系适用性未被独立校验，事实压缩/因果缺失为促发因素。
- 完整结果和修复边界见 root-cause.md；不实施应用修复。
