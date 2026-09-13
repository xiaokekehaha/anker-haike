# Findings

## 已确认的用户目标
- 理解现有售后对话中的意图识别、query 构造和改写。
- 用户指出“无结果才改写”不能被误表述为已有负向收益；明确耗时可以先忽略，效果优先。
- 用户调用 to-spec，要求从已有上下文综合成规格，未要求实现代码或开启当前开关。

## 实现与历史证据
- intake 已接入结构化抽取；query 构造是已确认产品与有效症状的规则拼接。
- 当前 query.rewrite 默认关闭；触发门槛是有效范围内请求的库均 no_match，且无相关命中及故障卡命中、名额和预算允许。
- grade 可将没有 relevant 的结果视作补查候选，但会从下游诊断输入删除判为 irrelevant 的片段。
- 图片补查优先，与文本改写共用一次补检索名额。
- 2026-09-13 的 56 条历史评测未人工标注：改写 0 次触发；加入 grade 后 plan_match 41/43 → 39/43。它们不能证明 query 改写降低效果。
- 历史报告及术语参考：../2026-09-13_bounded-agentic-rag/{switches,findings,design}.md。
- D15 保持预写排查计划；D19 限定两轮、子流程模型调用不超过 4 次、模型不决定动作。新规格需修订 D19 中“评分硬过滤”的语义，保留有界编排。

## 测试边界
- 已有检索事件测试从会话 API 发送消息，使用 FakeAdapter / mem_runtime，读取 SSE、快照与真实图执行结果。
- 现有 rediagnose、恢复、取消、模型降级测试可复用。
- 现有 haike-kb eval 支持真实模型诊断对比，但不能假定现有工具已完整覆盖新补救链路；规格要求统一编排路径。

## Tracker 状态
- Git remote 为 GitHub 的 xiaoke12345678/anker-haike。
- 项目存在本地历史 issues，使用过 ready-for-agent，但 AGENTS.md / CLAUDE.md 未提供发布 tracker 和 triage 配置。
- to-spec 要求缺少该配置时提示 /setup-matt-pocock-skills；未猜测发布目标，未创建外部 issue。

## 工作区保护
当前已有评测脚本、样例、Makefile、旧规划文档等未提交修改；仅在本任务新目录新增文件。
