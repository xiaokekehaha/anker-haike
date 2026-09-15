# 83: 多模型交叉审核评估

**What to build:** 评估而非上线：新增可选 task `review.check`（独立厂商模型）对三类输出做审查——propose / consult 用户可见文本是否越出账本与条款、synthesize 假设是否被证据支持、guide 步骤是否与原文一致；分歧裁决规则草案（审查否决 → 直渲染模板 / 降级 / 人工）；在回放包与评测集上离线跑，报告：捕获的真实错误数、误否决数、延迟与成本增量；结论决定是否进主链及在哪一层。

**Blocked by:** P0 66；P1 72（真实样本）

**Status:** todo

**Owner:** —

- [ ] 报告 `reports/eval/cross_review_<date>.md` 含混淆矩阵与成本
- [ ] 若上线建议，给出开关设计与预算门槛；默认关闭
- [ ] 不改变现有确定性检查（承诺账本、禁词表）作为第一道防线

**设计依据：** 06 §5 末段；meeting-painpoint-coverage E12
