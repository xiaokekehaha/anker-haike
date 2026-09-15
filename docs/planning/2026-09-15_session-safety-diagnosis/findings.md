# 发现

- 管理页面可访问；返回 SPA HTML，需要读取会话 API。
- 用户所引回复对应 orchestrator/app/escalation/summary.py 中 R4 固定回复。
- 规则配置为 config/rules/safety_terms.yaml。
- 会话最后一轮用户原文为「不能用了」，无图片。understand 无升级原因，guide 首次出现 R4。
- 最后一轮路径：understand → disambiguate → retrieve → reply → guide → escalate → summarize → commit_issue。
- retrieve 选择 rv_suction_motor_fault；摘要仅记录「命中词：pre_step」，实际词需从日志/计划核实。
- 待验证：计划原文安全词、步骤改写安全词、历史风险沿用。
- 注意：当前工作区 route_after_retrieve 已优先进入 guide，但会话记录仍为先 reply 再 guide，存在运行代码与当前文件差异。
- 实际日志命中词为「焦味」，时间 2026-09-15T01:27:06.156012+00:00，版本 2026-09-12.1。
- 诊断模型以 0.3 置信度将 rv_suction_motor_fault 排首位，并明确说用户未描述具体现象。
- prepare_step 在模型改写之前检查计划原文；manual_rv_v1#c30 的条件安全提示包含「焦味」。
- 离线真实 prepare_step 复现返回 escalate/R4；移除原文「焦味」后规则返回 ok。
- 步骤检查复用 cp_in 导致来源日志误导；实际词未从 StepPrep 传递，摘要使用 pre_step 占位。
- 部署预检：仅覆盖两处修复的旧镜像不能加载当前 bind-mounted plans.yaml；五项 symptom_codes 字段被旧 PlansConfig 拒绝。禁止直接重启以免触发已有配置/镜像不兼容。
- 本次没有替换运行镜像或重启服务；不扩大到整套未提交功能发布。
