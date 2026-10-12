# cases.yaml 用途核查

## 问题
说明 data/eval/tickets/cases.yaml 是否参与客服运行，以及依赖边界。

## 结论
- 该文件是 63 单官方工单的二次评测标注，提供意图、预期流程终点、知识候选、禁止承诺等期望。
- 直接消费者是确定性评测 app/evaluation/tickets.py、真实对话回放 app/evaluation/live_tickets.py、检索评测 app/knowledge/eval.py 及测试。未发现正式会话处理链读取此文件。
- 真实回放中部分标签还影响模拟客户反馈；检索评测可以用 pn 标签补充检索范围。因此不只是最终评分表，也包含评测输入与驱动依据。
- 官方问题原文来自 data/official/tickets.yaml；官方知识正文来自 data/official/qa.yaml 及其 WeKnora 入库数据。cases.yaml 不提供生产回答正文。
- T63 标注要求澄清并转交配件诉求；但 live_tickets.py 的 ACCEPT 将 explain / no_guidance 也算 clarify，评分通过不等于确实询问了型号，也不等于回复内容完整。
- 修改 cases.yaml 会改变评测口径或模拟过程，不会直接修复真实客服行为；应按原文、知识、业务规则独立核对标注。

## 验证
检索全仓文件名及代码引用，阅读标注文件和消费者代码；未运行真实模型或修改业务代码。
