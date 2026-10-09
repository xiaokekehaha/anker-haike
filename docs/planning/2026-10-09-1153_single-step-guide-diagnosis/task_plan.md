# 任务流水

## Goal
回答指定会话为何只有一次步骤卡片，以及是否符合多步骤引导设计。

## Phases
- [x] 读取会话事件和当前状态（complete）
- [x] 验证具体排障计划及设计（complete）
- [x] 写出结论及建议（complete）

## Next Step
诊断完成，向用户汇报结论和可选体验改进。

## Errors
首次路径搜索使用不存在的 orchestrator/app/api；改用已定位的客户端路径与 app 模块列表。
临时验证脚本首次调用了不存在的 PlanLibrary.instruction；完整读取 library.py 后改用 evidence_snippet，复跑通过。
