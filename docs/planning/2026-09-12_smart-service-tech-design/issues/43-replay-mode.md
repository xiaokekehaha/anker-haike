# 43: 回放模式与录制包

**What to build:** ReplayRouter 与 ReplayKnowledgeAdapter 只在 REPLAY_CASE_ID 设置时启用，录制包含 manifest（prompt_ver / models_ver / kb_ver / rules_ver）与事件序列，清单不符启动报 replay_incompatible；未命中返回 unavailable 不借用其他案例；录制脚本产出 A1–A3 录制包；前端 ?replay=1 透传。

**Blocked by:** 36（出口规则 R1 / R1b / R1c / R2 与 A1 完成）、41（订单与渠道核对 L1–L6 与 A3 完成）

**Status:** ready-for-agent

- [ ] 断网状态下 A1–A3 按录制包完整跑通
- [ ] 改动 prompt 版本后启动报 replay_incompatible 而非静默降级
- [ ] 回放命中的 evidence 标 status=replay，前端显示「演示回放」
- [ ] 录制包随镜像打包

**设计依据：** 09 §6；04 §1、§4
