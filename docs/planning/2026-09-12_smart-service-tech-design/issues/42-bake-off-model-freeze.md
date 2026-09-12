# 42: bake-off 评测与模型 ID 冻结

**What to build:** 为每个 task 准备 20–30 条金标样本（视觉任务各 15 张图），脚本对链上每个候选模型跑 3 遍取中位数，输出 Schema 通过率、字段准确率、延迟 P50、成本四项并与门槛比对；据结果确定主备并把真实模型 ID 写入 models.yaml 与 RELEASE.md。

**Blocked by:** 12（限流退避与全局有界队列）

**Status:** done-with-gap（2026-09-13；评测包 + DeepSeek 单家 3 遍实测 + ID 冻结完成；「主备两家厂商」待其他厂商 key）

**Owner:** Claude Code C（2026-09-12 23:45 认领；新增 `orchestrator/app/bakeoff/`（样本加载、逐 task 评分、报告）、`orchestrator/tests/fixtures/bakeoff/`（金标样本）、`haike-bakeoff` CLI 与 Makefile 目标；不改 `app/sessions/`、`app/guide/`、`app/observability/`。本机只有 DEEPSEEK_API_KEY：脚本与 DeepSeek 单家实测先做，qwen / glm / 视觉样本待 key 到位后同一命令补跑）

- [x] 评测脚本一条命令跑完并输出对比表（`make bakeoff`；9 个 task × 链上候选 × 3 遍，Markdown + JSON 到 reports/bakeoff/）
- [x] 结果与裁决理由写入 findings.md「bake-off 结果」小节（../../2026-09-12_smart-service-bakeoff/findings.md）
- [ ] 每个 task 主备至少来自两家厂商（**未满足**：本机只有 DeepSeek key，其他厂商只完成 ID 核对；链已按「qwen 主 / deepseek 备」排好，key 到位后 `make bakeoff` 即出两家对比）
- [x] models.yaml 中不再有 TBD（2026-09-13.1，TBD 计数 0），release.sh 增 bake-off 行；RELEASE.md 由下次 `make release` 生成

**设计依据：** model-selection §3.8、§4
