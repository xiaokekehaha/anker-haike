# 66: 演示脚本 A4–A9 回放包、巡检场景、RELEASE 六元组与 runbook

**What to build:** 录制 A4–A9 回放包并纳入 `make replay-*`；版本清单四元组扩为六元组（+ policy_version、actions_version）并校验；巡检 `inspection/scenarios.py` 新增：伪造 confirm_proposal 载荷越权、幂等重放、HITL 拒绝、模拟后端 timeout / unavailable、complaint_risk 三轮、模糊图补拍跳过、多意图接续；RELEASE.md 增六元组与配置版本（emotion_policy / symptom_taxonomy / vision_vocab / backends_mock seed）；runbook：模拟后端 seed、故障注入开关、审批操作、案件人工结案；演示脚本文档（08 §5）与兜底说明。

**Blocked by:** 51–64（65 可选）

**Status:** todo

**Owner:** —

- [ ] `make replay-all` A1–A9 全绿；`make inspect` 新增七类场景通过
- [ ] RELEASE.md 与部署镜像一致（票 49 教训：以实际部署核对）
- [ ] 演示脚本按 08 §5 走一遍并录屏留档

**设计依据：** 07 §5–§6；08 §5
