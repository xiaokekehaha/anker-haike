# 票 04：前端契约生成与校验

## 目标
仅完成 issues/04：从票 03 的 JSON Schema 生成 TypeScript 类型，提供可检测漂移并打印差异的 CI 检查、共享 fixtures 骨架与 Zod 事件校验入口。

## 阶段
1. 核对协作状态与契约源、登记认领 — complete
2. 实现确定性类型生成和 Schema 驱动的事件校验 — complete
3. 接入独立 CI 与共享 fixtures 约定 — complete
4. 验证类型、非法事件与漂移检测，更新票据 — complete

## 协作边界
- 本轮只做票 04；票 03 的 Python 契约已有文件、尚未回填完成，保留 Claude 的实现所有权。
- 修改 frontend/、独立 .github/workflows/contracts.yml、contracts/fixtures/、独立 planning 与认领行；复用 Python 导出入口，避免写 Python 模型。
- 不操作数据库，不切换分支，不暂存或提交他人改动。
- 如 Python 契约仍在演进，以最终可用 Schema 重新生成验收，不手改生成文件绕过上游差异。

## Next Step
票 04 已完成，本轮结束，不继续认领其他票。GitHub Actions 待提交/推送后在远端触发；本机对应检查已通过。

## Errors Encountered
| Error | Attempt | Resolution |
| --- | --- | --- |
| Vitest 的 jsdom 环境将 fixture URL 转为 HTTP，fs 读取要求 file URL | 1 | 协议测试不依赖 DOM，改为该文件使用 Node 环境；页面测试保持 jsdom。 |
| Ruff TRY004 指出数组类型校验应使用 TypeError | 1 | fixture 校验脚本改为 TypeError。 |
| 生成器未导出根 oneOf 未引用的 ActionResult / ActionConflict，回归测试捕获 | 1 | TS 编译时用对象根承载所有 $defs，使 unreachableDefinitions 生效；运行时仍使用原始 Schema。 |
