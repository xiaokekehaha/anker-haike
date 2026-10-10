# 任务流水

## 阶段

- [x] 1. 定位四个分支与执行入口（complete）
- [x] 2. 重跑四个独立会话并记录原始证据（complete）
- [x] 3. 核对症状与完整会话（complete）
- [x] 4. 交付可读记录与复现结论（complete）
- [x] 5. 核对四案根因与代码断点（complete）
- [x] 6. 交付根因说明，区分确认与待验证（complete）

## Next Step

交付 `根因分析.md` 与本地探针结果；没有实施业务修复。

## Errors Encountered

- 首次批量搜索碰到单行 sources.json 大文件，输出过长；后续按文件名和长度限制搜索。
- 读取原始 journey 时输出过长；改为只展示文字、卡片与实际查询，完整原始证据保存在 JSON。
- 查找不存在的 api/ADR 目录返回 exit 2；服务健康检查与容器状态均正常，无需这些目录即可重用原执行器。
- 文档生成器首次退出：原评测 reference-qa.json 未包含本次新路径使用的 bp-0049；改从版本指纹已核对的 data/official/qa.yaml 读取所需官方说明。
- 追加根因定位时查找不存在的 diagnose/run.py 与 applicability.py 返回 exit 1；后续定位到实际 synthesize.py。
