# 42: bake-off 评测与模型 ID 冻结

**What to build:** 为每个 task 准备 20–30 条金标样本（视觉任务各 15 张图），脚本对链上每个候选模型跑 3 遍取中位数，输出 Schema 通过率、字段准确率、延迟 P50、成本四项并与门槛比对；据结果确定主备并把真实模型 ID 写入 models.yaml 与 RELEASE.md。

**Blocked by:** 12（限流退避与全局有界队列）

**Status:** done（2026-09-13；用户提供 ZHIPU_API_KEY 后补跑两家对比、修正链与模型 ID、失效切换实测通过；dashscope / anthropic / google 仍无 key，表内标「未跑」）

**Owner:** Claude Code C（2026-09-12 23:45 认领；新增 `orchestrator/app/bakeoff/`（样本加载、逐 task 评分、报告）、`orchestrator/tests/fixtures/bakeoff/`（金标样本）、`haike-bakeoff` CLI 与 Makefile 目标；不改 `app/sessions/`、`app/guide/`、`app/observability/`。本机只有 DEEPSEEK_API_KEY：脚本与 DeepSeek 单家实测先做，qwen / glm / 视觉样本待 key 到位后同一命令补跑）

- [x] 评测脚本一条命令跑完并输出对比表（`make bakeoff`；9 个 task × 链上候选 × 3 遍，Markdown + JSON 到 reports/bakeoff/）
- [x] 结果与裁决理由写入 findings.md「bake-off 结果」小节（../../2026-09-12_smart-service-bakeoff/findings.md）
- [x] 每个 task 主备至少来自两家厂商（DeepSeek + 智谱两家实测：9 个 task 里 7 个两家均达主模型门槛；diagnose.vision 的 glm-4.6v 只达备用位门槛（77% < 主 80%，但与主差 6 点、延迟比 1.27，满足 §3.8 备用位）；query.rewrite 两家都 0%（票 32 词表问题，开关默认关闭）。models.yaml 2026-09-13.2 把每个 task 第三位换成实测达标的智谱位。**失效切换实测**：把 DEEPSEEK_API_KEY 换成无效值跑完整 A3，整链切到智谱并正常完成，凭证 OCR 由 glm-4.6v 四字段全对）
- [x] models.yaml 中不再有 TBD（2026-09-13.2，TBD 计数 0），release.sh 增 bake-off 行；RELEASE.md 由下次 `make release` 生成
- [x] 评测暴露并修正的真实缺陷（只有实测才能发现）：① `glm-4.7-flash` 不存在（调用返回 500），换 `glm-4.5-flash`；② 智谱不支持 `response_format: json_schema`，`structured: native` 下 Pydantic 校验 3/3 失败，改 `json_object` 后 3/3 通过；③ 智谱默认开思考模式，补 `params: {thinking: {type: disabled}}`；④ guide.step 原选 glm-4.7 实测稳定 89% < 90%，换 glm-4.5-flash（94%）

**设计依据：** model-selection §3.8、§4

**方法学发现（2026-09-13）：** repeats=3 的两轮对同一候选给出不同裁决（disambiguate.clarify 的 glm-flash schema 100% → 92%；guide.step 的 glm 92% → 89%；diagnose.vision 的 glm-v 80% → 77%）。加跑 repeats=5 才定住：前者是抖动，后两者稳定未达标。**门槛线附近的候选用 repeats=3 判定不可靠，冻结前应跑 repeats=5。**

**代价（待决策者确认）：** `retry.chain_max=3`，每个 task 第三位只能在「没有 key 的 overseas 跨通道兜底」与「实测达标的智谱位」之间二选一，本次选后者——当前环境 dashscope / anthropic 均无 key，原兜底位不可达，等于每个 task 只有 deepseek 一个可用模型。若要同时保留跨通道兜底，需把 chain_max 提到 4 或重排链序。

**回放包：** models_ver 从 2026-09-13.1 变为 2026-09-13.2，A1 / A2 / A3 三个录制包已用真实模型重录，`haike-replay verify` 三包零未命中（票 43 的「模型 / 链变化须重录」约束）。
