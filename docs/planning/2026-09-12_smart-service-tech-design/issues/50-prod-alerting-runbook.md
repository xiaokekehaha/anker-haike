# 50: 生产就绪：告警与运行手册

**What to build:** 接入最简告警（邮件或 IM webhook）：模型连续失败 3 次、检索为空率 > 50%、队列拒绝率、健康检查连续失败；编写运行手册：常见故障定位步骤、回滚、密钥轮换、备份恢复、清理任务排查。

**Blocked by:** 44（可观测：Langfuse profile 与延迟指标）

**Status:** done（2026-09-13，接手会话；告警链路本机实测）

**Owner:** Claude Code（接手会话，2026-09-13）

- [x] 人为制造模型全部失败后 5 分钟内收到告警（`app/observability/alerts.py`：四条规则 model_chain_failed / retrieval_empty_rate / queue_rejections / health_check_failed，挂在 `record()` 钩子与 `/health` 后台探测上；webhook（飞书 / 钉钉 / 企微 / Slack 兼容 JSON）+ 邮件两种投递，5 min 冷却、恢复通知、`/health.alerts`；实测：无效 DEEPSEEK_API_KEY 起服务发 3 条消息，第 3 次链耗尽即触发，webhook 4 s 内收到，之后 9 次触发被冷却抑制）
- [x] 运行手册覆盖 04 文档稳定性表中每一行风险的处置方法（docs/runbook/operations.md §3：16 行风险 + PostgreSQL 单点 + 清理任务，每行给现象 / 定位 / 处置；§1 告警规则、§2 收到告警先做什么、§4 密钥轮换、§5 备份恢复回滚清理速查）
- [x] 值班人员按手册可独立完成一次回滚演练（operations.md §6 自测清单，引用 release.md §3 的 `make rollback`；演练本体在票 49 已完成（2 s），本票未重复执行，理由：共享开发机上回滚会覆盖未提交的 config 且需镜像与 config 成对）

**设计依据：** 04 §1、§3、§4

**验收（2026-09-13）：** 后端 422 项（新增 9）、ruff 通过；`.env.example` 增 ALERT_*。差异：告警在编排进程内计算，不引入 Prometheus / Alertmanager；邮件投递只做了 SMTP 实现与配置装配，未做真实 SMTP 联调。
