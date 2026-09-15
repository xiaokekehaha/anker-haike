# 72: 评测集替换为真实样本与保留集基线

**What to build:** 用 71 的保留集替换 / 扩充 `data/eval/{symptom,routing,emotion,conversation/semantic-gold}`（各 ≥ 40 条，标注人与日期入 YAML）；`haike-eval all --baseline` 产出保留集基线报告 `reports/eval/baseline_<date>.md`（意图准确率、症状族准确率、路由 / 情绪准确率、越权率、承诺违规数）；CI 跑开发集，保留集只在 release 前手动跑并冻结结果。

**Blocked by:** 71；P0 64（haike-eval CLI）

**Status:** todo

**Owner:** —

- [ ] 保留集样本不出现在任何 prompt / 词表 / 计划文件（脚本扫描断言）
- [ ] 基线报告含样本量、标注人、模型链版本
- [ ] 意图准确率对标 ≥ 90% 的差距在报告中列明

**设计依据：** 07 §2、§4；01 §5
