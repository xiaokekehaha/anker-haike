# Claude 未完成任务盘点与票 41 续接

## Goal
盘点票据与工作树，认领并完成票 41：订单与渠道核对 L1–L6、参考数据 seed、确认后摘要及回归验证。

### Phase 1: 盘点与认领
**Status:** complete

### Phase 2: 订单名录、规则和摘要链路
**Status:** complete

### Phase 3: 规则、API、迁移验证并回填票据
**Status:** complete

## Decisions
- 34–36 已由 Claude A 认领；32 属 Claude B，本轮选择无 Owner 的 41。
- 保留既有未提交改动，共享文件只做本票必要增量。
- 参考数据明确为 mock，订单核对只给事实与下一步；不作质保资格判断。

## Errors Encountered
- 长日志输出被截断，后续缩小读取范围。
- 曾枚举不存在的 app/receipt 和 catalog/runtime.py；实际凭证入口为 app/sessions/receipt.py。

- 测试文件重复目录前缀、摘要工厂重复 JSON 编码、测试配置误删必需任务、前端测试可选字段类型错误均已修正。
- 一次前端补丁因并行空值处理改动定位失败，重读后以增量方式完成。
- 全量回归受其他任务 guide.step 四模型链/上限三不一致阻塞，9 失败；本票 50 项相关全部通过。全局 lint 另有其他文件 3 项，已列入盘点。

## Next Step
本轮票 41 已完成。后续由当前负责人修复 guide.step 配置与收尾 34–36，再推进 37；待开发清单见 task_inventory.md。
