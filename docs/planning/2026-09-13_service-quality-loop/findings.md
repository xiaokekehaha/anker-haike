# 现状证据

- 已有观测续接文档：模型调用可关联 session/run，本地 JSONL 与可选 Langfuse；现有验收主要覆盖追踪、脱敏与延迟。
- 票 44 已记录步骤反馈 cp_verify 埋点，但需要核对其是否形成持久质量对象和复盘流程。
- 工作区存在其他未提交改动；本轮使用独立规划目录。
- `contracts/haike_contracts/common.py` 已有 solved/not_solved/cannot_do 步骤反馈，步骤含 plan_version 和 evidence_ids；还需单独的回答质量与服务最终结果对象。
- `app/sessions/store.py` 有 sessions/session_events/session_actions，业务反馈不能只依赖 best-effort 观测日志。
- `app/knowledge/ingest.py` 已有手册、FAQ、工单导入及文档版本；当前更版删旧建新、FAQ 整体替换，不能视作原子灰度发布。
- `app/knowledge/snapshot.py` 快照支持源文件重导入回滚；需补发布状态与解析/检索验证。
- `app/replay/package.py` 用 prompt/models/kb/rules 四类版本核对和输入哈希回放录制输出；不能单靠旧输出回放证明新模型回答变好。
- `app/bakeoff/scoring.py` 为任务级规则评分，可复用断言思路，但需要质量案例到评测样本的转化及端到端验证。
- `AssistantBubble.tsx` 暂无回答评价入口；`StepCard.tsx` 已有三态反馈和备注。
- `observability/metrics.py` 当前只汇总 first_visible_ms/card_ready_ms，不包含质量闭环指标。
- `sessions/graph.py::close` 的完成包括 solved 和 next_on:DONE，故 done/completed 不能直接当用户确认解决。
- `knowledge/adapter.py` 检索按产品范围过滤，目前入口为 kb_manual/kb_tickets；知识候选的审核状态、发布状态需要接入检索边界。
- `retention.py` 已有按会话删除与 TTL 清理；新增质量证据和评测衍生数据必须纳入清理设计。
- `settings.py` 默认会话保留 24 小时、追踪 7 天（实际部署可覆盖）；复盘若仅挂原始会话链接会在清理后失去证据，设计要求及时生成最小脱敏案例并单独治理。
- `observability/runtime.py` 当前在导出时随机生成 trace/span ID，质量定位需要新增稳定 model_call_id；内存队列可丢弃，不适合承载唯一质量事实。
- `plans/store.py` 说明运行时读取缓存，不按请求查表；知识变更与计划缓存加载需纳入同一发布验收。
