# 工作记录

- 09:29 开始独立方法审查。完整读取 AGENTS.md、Makefile 与旧 HTTP 驱动；使用 planning-with-files 记录。当前 HEAD=4cecc95，尚未执行新一轮模型测试。
- 建立独立目录；本轮先固定预期再看输出，不以历史 review 或合格率为判定依据。
- 冻结 method.md 的 63 案预期及 scenarios.json 的 18 分支、5 复跑。新驱动 14 项离线守卫测试通过；模型前工作区/容器指纹一致，HEAD=4cecc95。
- 09:36 启动 86 会话分层测试，并发 3；官方层不自动答未解决。当前 CI 后端有 1 失败（1159 passed / 2 skipped），后续契约 90、前端 230、typecheck/build 均单独完成通过，不能把 CI 报全绿。
- 发现对话完成后异步审计 journey 暂时 404，稍后读取可恢复；原记录保留，计划只读补采，不重跑用户对话。
- 09:40:51 全量运行结束，共 86 独立会话/104 次交互，代码和容器指纹稳定。原始即时采证 39/86 完整，47 份 journey 404；对话无事件错误。
- 只读 enrichment 取得 86/86 journey、published checkpoint、案件与 SQL；不重放对话，不覆盖原始 run 文件。
- 时间戳隔离诊断 2/2 通过：案件早于 episode 保留 in_progress，晚于 episode 才投影 executed_closed。CI 原始 1 失败不改写。
- 全部 A/B/R 输出已逐案复核，新增暴露 B04/B05/B06/B07/B09/B10/B11/B12/B15/B18 缺陷。R05 与 T53 出现额外退款任务差异。
- 09:47 完成判断文件并记录评分哈希：A 56/63、B 8/18、R 4/5 对一致；随后才读取上一轮报告比较，未改本轮评分。audit_results 核验 1694 个契约事件和全部固定模拟输入。
- 直接核对原始 xlsx 中 18 条关键 QA 的 sheet/单元格，保存 qa-source-map.json；875 条 QA 无 green/绿/5116 词面命中。知识词面缺失不作为完整语义审计结论。
- 写完 report.md、method-review.md、source-review.md、review.md、branches-review.md，分别报告效果、方法缺陷、责任边界与源资料疑点。没有修改产品、既有测试、官方源文件，没有提交或发布。
- 删除一次性导出/打印/Excel 定位脚本，保留结果证据；evaluate、enrich、audit_results 和两份测试保留为本轮可复现资产。
