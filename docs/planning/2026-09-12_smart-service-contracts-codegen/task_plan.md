# 票 04：前端契约生成与校验

## 目标
仅完成 issues/04：从票 03 的 JSON Schema 生成 TypeScript 类型，提供可检测漂移并打印差异的 CI 检查、共享 fixtures 骨架与 Zod 事件校验入口。

## 阶段
1. 核对协作状态与契约源、登记认领 — complete
2. 实现确定性类型生成和 Schema 驱动的事件校验 — in_progress
3. 接入独立 CI 与共享 fixtures 约定 — pending
4. 验证类型、非法事件与漂移检测，更新票据 — pending

## 协作边界
- 本轮只做票 04；票 03 的 Python 契约已有文件、尚未回填完成，保留 Claude 的实现所有权。
- 修改 frontend/、独立 .github/workflows/contracts.yml、contracts/fixtures/、独立 planning 与认领行；复用 Python 导出入口，避免写 Python 模型。
- 不操作数据库，不切换分支，不暂存或提交他人改动。
- 如 Python 契约仍在演进，以最终可用 Schema 重新生成验收，不手改生成文件绕过上游差异。

## Next Step
核对 Schema 生成工具的兼容性，按现有导出格式实现前端生成与校验。

## Errors Encountered
暂无实现错误。
