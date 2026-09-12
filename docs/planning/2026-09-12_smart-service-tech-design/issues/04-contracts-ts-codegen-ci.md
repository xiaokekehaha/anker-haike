# 04: 前端 TS 类型生成、CI 比对与 fixtures 骨架

**What to build:** 从 JSON Schema 生成前端判别联合类型，CI 中重新生成并与已提交文件比对，不一致即失败。建立共享 fixtures 目录，前后端测试后续共用。

**Blocked by:** 03（contracts 包：事件 / 动作 / 快照 Pydantic 模型与 JSON Schema）

**Status:** done（2026-09-12）

**Owner:** Codex（2026-09-12 认领，本轮仅此一票）

**协作边界：** Codex 负责前端契约生成与运行时校验、独立 CI workflow、`contracts/fixtures/` 骨架；复用票 03 的 Pydantic 定义与导出入口，不修改 `contracts/haike_contracts/`。票 03 仍由 Claude Code 完成，最终以其导出的 Schema 联调验收。独立记录见 `../../2026-09-12_smart-service-contracts-codegen/`。

- [x] 生成的 TS 类型与 05 文档摘录的 ServerEvent / PendingKind 形状一致
- [x] CI 步骤在类型漂移时失败，并打印差异
- [x] fixtures 目录有目录约定与一个空的 A1 序列占位文件
- [x] 前端用 zod 按 Schema 校验事件，非法事件丢弃并打日志

**设计依据：** 05 §2、08 §9

**实现记录：** `make contracts` 串联票 03 导出器和 `frontend/scripts/contracts.mjs`，生成三份 TS 类型及 Zod 校验器。`make contracts-check` 检测漂移；前端检查打印 diff 且不覆盖现有产物。保留 ServerEvent 判别联合、PendingKind、动作响应和快照 timeline 类型。`parseServerEvent` 丢弃非法载荷并仅记录固定错误码和问题数。共享 fixtures 包含 A1 空占位和 15 种协议事件样本。

**验证（2026-09-12，Codex）：** 50 项前端测试、6 项生成器回归、62 项上游契约测试通过；15 种共享样本同时通过 Zod / Pydantic；类型检查、生产构建与 `make contracts-check` 通过。临时目录实测人为篡改、约束变化、缺失产物均使检查非零退出并打印差异。独立 `.github/workflows/contracts.yml` 已接入，Schema 重新导出 / git diff 门禁已在本机执行通过；尚未触发远端 GitHub Actions。

**协作结果：** 票 03 已由 Claude A 完成；未修改其 Python 契约。共享 Makefile 只在既有导出与检查命令后追加前端步骤。本轮不认领票 06。
