# 81: Bedrock 通道 bake-off 与切换演练

**What to build:** 在 P0 65 的 provider 基础上，对 `lanes.aws` 全部 task（含新 task：consult.extract_params、propose.wording、新 schema 的 diagnose.vision）跑 `haike-bakeoff`，按既有门槛（schema 100% / 准确率 ≥ 90% 主位、≥ 80% 备位、latency_ratio ≤ 1.5）裁决链序；跨通道降级：aws 链尾接 domestic 别名；切换演练：`MODEL_LANE=aws` 下 A1–A9 回放 + 巡检；成本对照写入报告；演示当天切换 / 回切 runbook。

**Blocked by:** P0 65, 66；D-L3-2 确认；AWS 账号与 Bedrock 模型访问权限

**Status:** todo

**Owner:** —

- [ ] 报告 `reports/bakeoff/aws_<date>.md`，每 task 主备两家（Bedrock 上 Claude 两档 + 降级 domestic）
- [ ] aws 通道 A1–A9 全绿；首可见 / 首卡延迟与 domestic 对照表
- [ ] runbook：切换、回切、凭证轮换

**设计依据：** 02 §4；00 D-L3-2
