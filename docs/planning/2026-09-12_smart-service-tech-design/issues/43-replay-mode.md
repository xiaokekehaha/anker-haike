# 43: 回放模式与录制包

**What to build:** ReplayRouter 与 ReplayKnowledgeAdapter 只在 REPLAY_CASE_ID 设置时启用，录制包含 manifest（prompt_ver / models_ver / kb_ver / rules_ver）与事件序列，清单不符启动报 replay_incompatible；未命中返回 unavailable 不借用其他案例；录制脚本产出 A1–A3 录制包；前端 ?replay=1 透传。

**Blocked by:** 36（出口规则 R1 / R1b / R1c / R2 与 A1 完成）、41（订单与渠道核对 L1–L6 与 A3 完成）

**Status:** done（2026-09-13；Claude Code B，A1–A3 三个录制包已用真实 DeepSeek + WeKnora 录制并断网重放核对通过）

**Owner:** Claude Code B（2026-09-13 00:05 认领；新增 `orchestrator/app/replay/`（录制包、ReplayRouter、ReplayKnowledgeAdapter、录制 / 校验 CLI）与 `replay/` 录制包目录；改 settings / main 启动清单校验、health 回放组件、Dockerfile 打包；前端只改 health 解析与 HeaderBar 徽标；不动 graph.py / guide / rules）

- [x] 断网状态下 A1–A3 按录制包完整跑通
- [x] 改动 prompt 版本后启动报 replay_incompatible 而非静默降级
- [x] 回放命中的 evidence 标 status=replay，前端显示「演示回放」
- [x] 录制包随镜像打包

**设计依据：** 09 §6；04 §1、§4

## 实现与验证（2026-09-13）

- `orchestrator/app/replay/`：`package.py`（清单 / 事件记录 / 键 / 版本核对 / Recorder）、`router.py`（ReplayRouter 与 RecordingRouter，与 ModelRouter 同接口）、`knowledge.py`（ReplayKnowledgeAdapter 与 RecordingKnowledgeAdapter）、`runtime.py`（REPLAY_CASE_ID 开关，进程级加载 + 核对）、`scenarios.py`（A1–A3 内置脚本，录制与核对共用）、`cli.py`（`haike-replay record | check | verify | list`；Makefile `replay-record / replay-verify / replay-check / replay-list`）。
- 键：模型 = sha256(task, schema 名, 规范化消息)，图片以字节 sha256 代入；检索 = sha256(kb, query, scope, top_k)。不含 session_id / run_id / 时间，同一对话重跑同键。
- 清单 `{prompt_ver, models_ver, kb_ver, rules_ver}`：prompt_ver 汇总 system / reply / guide / clarify / vision / ocr / summary 七个模板版本（全相同给单值，否则逐项列出）；kb_ver 来自 data/knowledge/manifest.json，容器内用 `replay/kb_manifest.json` 快照（录制时写出，`KB_MANIFEST_PATH` 指向它）。任一项不符或包缺失 / 损坏 → `ReplayIncompatible`，main 启动失败；health `replay.status=down`。
- 未命中：模型抛 `ModelInvokeError(reason=replay_miss)`（节点走既有降级），检索返回 `unavailable`；都不借用其他记录。命中检索 `status=replay`，`Hit.status` 进 evidence.items，前端 EvidenceDrawer 已显示「演示回放」（票 28），HeaderBar 新增「演示回放 / 回放不可用」徽标（/health 新增 `replay` 块，仅回放模式出现）。
- 录制包 `replay/a1_hair_wrap`（4 模型 + 2 检索）、`a2_disambiguate`（4 + 2）、`a3_receipt_channel`（8 + 2：intake / synthesize / reply / guide.step×3 / receipt_ocr / escalate.summary），真实 DeepSeek（deepseek-flash）+ 本机 WeKnora 录制；`haike-replay verify` 三案例 model_misses / knowledge_misses 均空、evidence_status 全 replay、预期事件齐全。Dockerfile `COPY replay ./replay`，compose 透传 `REPLAY_CASE_ID`。
- 进程级实测：`REPLAY_CASE_ID=a1_hair_wrap` 启动 → app.state.model_router 与图节点取到 ReplayRouter、知识取到 ReplayKnowledgeAdapter、/health 带 replay 块；把清单 prompt_ver 改成 2026-09-12.0 后启动抛 `ReplayIncompatible: prompt_ver: recorded='2026-09-12.0' current='2026-09-12.1'`。
- 测试 `tests/test_replay.py` 7 项：键稳定性、清单不符 / 包损坏 / 缺版本、ReplayRouter 命中与未命中（真实假模型零调用）、ReplayKnowledgeAdapter 四态、A1 录制→断网重放（事件类型序列一致、evidence 全 replay、guide.step 录制时失败则回放同样 miss）、runtime 开关与 health。前端 HeaderBar / health 各加 1 项。
- 边界：A3 的 receipt_ocr 走的是 deepseek-flash（票 42 冻结的当前唯一可用位），真实视觉 OCR 仍待其他厂商 key；stream 回放按录制分片、间隔 20 ms（`stream_delay_s`）；回放包只覆盖脚本内的话术，偏离脚本即 miss 走降级。
