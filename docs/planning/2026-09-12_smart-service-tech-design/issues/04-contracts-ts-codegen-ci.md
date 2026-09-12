# 04: 前端 TS 类型生成、CI 比对与 fixtures 骨架

**What to build:** 从 JSON Schema 生成前端判别联合类型，CI 中重新生成并与已提交文件比对，不一致即失败。建立共享 fixtures 目录，前后端测试后续共用。

**Blocked by:** 03（contracts 包：事件 / 动作 / 快照 Pydantic 模型与 JSON Schema）

**Status:** in-progress

**Owner:** Codex（2026-09-12 认领，本轮仅此一票）

**协作边界：** Codex 负责前端契约生成与运行时校验、独立 CI workflow、`contracts/fixtures/` 骨架；复用票 03 的 Pydantic 定义与导出入口，不修改 `contracts/haike_contracts/`。票 03 仍由 Claude Code 完成，最终以其导出的 Schema 联调验收。独立记录见 `../../2026-09-12_smart-service-contracts-codegen/`。

- [ ] 生成的 TS 类型与 05 文档摘录的 ServerEvent / PendingKind 形状一致
- [ ] CI 步骤在类型漂移时失败，并打印差异
- [ ] fixtures 目录有目录约定与一个空的 A1 序列占位文件
- [ ] 前端用 zod 按 Schema 校验事件，非法事件丢弃并打日志

**设计依据：** 05 §2、08 §9
