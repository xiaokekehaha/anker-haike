# 42: bake-off 评测与模型 ID 冻结

**What to build:** 为每个 task 准备 20–30 条金标样本（视觉任务各 15 张图），脚本对链上每个候选模型跑 3 遍取中位数，输出 Schema 通过率、字段准确率、延迟 P50、成本四项并与门槛比对；据结果确定主备并把真实模型 ID 写入 models.yaml 与 RELEASE.md。

**Blocked by:** 12（限流退避与全局有界队列）

**Status:** ready-for-agent

- [ ] 评测脚本一条命令跑完并输出对比表
- [ ] 结果与裁决理由写入 findings.md「bake-off 结果」小节
- [ ] 每个 task 主备至少来自两家厂商
- [ ] models.yaml 中不再有 TBD，RELEASE.md 记录冻结版本

**设计依据：** model-selection §3.8、§4
