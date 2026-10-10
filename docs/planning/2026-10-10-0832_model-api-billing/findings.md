# 核查证据

- 2026-10-10 08:32（北京时间）`make ps`：所有本项目容器运行，orchestrator healthy。
- `make health`：status=ok、model_fail_streak=0、alerts.active=[]；domestic 通道配置了 dashscope、deepseek、zhipu。此检查不验证供应商余额。
- `config/models.yaml`：百炼承担 Qwen 聊天、embedding、rerank；DeepSeek 和智谱承担聊天主备。
- 用户所述“模型失败、预算不足”也出现在前一轮 acceptance.md 的候选执行门槛描述中；尚不能据此认定厂商欠费。
- 过去 24 小时筛选下实际保留日志覆盖 10 月 9 日 18:47 至 10 月 10 日 08:34（北京时间）：1418 次成功、4 次最终失败；没有余额/欠费/配额关键词错误，也没有 429。失败含模型输出字段校验、超时、安全拦截。
- 具体失败链：DeepSeek 两次输出 rationale 超过 80 字，随后 qwen-max 超时，最终 budget exhausted。router 的 budget_ms 是调用总时限；context budget exceeded 是输入上下文容量，两者不表示账户余额。
- 日志轮转的文件顺序不等于时间顺序；汇总脚本已改按 timestamp 选最新记录。
- 2026-10-10 08:34:11–08:34:36（北京时间），通过运行服务的 `/models/{alias}/probe` 对当前链上的 7 个聊天模型逐一最小直连探测，全部 connected：百炼 qwen-flash 1894ms、qwen-plus 1661ms、qwen-max 824ms、qwen-vl 381ms；DeepSeek deepseek 470ms；智谱 glm 4293ms、glm-v 574ms。每次最多输出 16 token，无业务降级链。
- WeKnora 近 24 小时错误/警告记录未发现欠费关键词；普通请求/知识文本中的 insufficient/balance 不作为供应商账务证据。
- 结论：当前未发现供应商欠费，当前三家模型接口均可用；无需因“模型失败、预算不足”这段描述充值。未查询各供应商账户余额具体金额，未修改产品代码或配置。

