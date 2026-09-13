# 发现
- 验收开始时工作树干净，HEAD 为 4abcd4e。
- 最新提交明确票 32 为 done-with-gap；主 implementation 计划存在陈旧 pending 概览，不能直接用作完成判据。
- 本次按整个 50 票实现验收，优先以每票最新条件与代码/实测证据为准。
- 票面统计：47 done、2 done-with-gap（32/42）、1 in-progress（40）；票 30 虽 done 也明确真实视觉样本未验收。
- 实测：前端 123/123、codegen 6/6、contracts 62/62；typecheck/build/contracts-check/ruff 均通过。构建存在 >500 kB chunk 提示（非阻断）。
- 当前 8000 /health 为 degraded，国内仅 DeepSeek ready；基础 db/redis/weknora 正常。待比对容器源码版本。
- 发现巡检 freeze 判定只判断 failed 为空，未检查关键组运行完整性或外部验收缺口，不能作为全项目完成证明。
- 后端全量 432/432（44.39 s，无 skip）；stub 巡检 29/29，5 并发通过；本轮报告落于 inspection/。
- 部署明确落后：容器内 graph.py SHA 与当前不同，guide/steps.py、retention.py、observability/alerts.py、inspection/cli.py 均不存在；线上前端 assets 哈希也不是本轮构建。
- RELEASE.md 仍是 drill-b / d13c7fa / 2026-09-12.2-bad，TBD=9、无回放包，是演练旧清单。
- 票 32 不仅缺外部标注，还明确未实现文本检索与读图并行、补检索整轮 ≤3 s 硬上限；虽勾选完成，属于内部实现差异。
- bakeoff findings 已有 DeepSeek 合成图 OCR/vision 实测，与索引“没有视觉 key”描述不一致；真实照片/真实订单截图的验收仍未完成。
- 真实 A1 0/1：stage=intake / node_failed；容器日志明确 RulesConfig.pre_step extra_forbidden，是旧代码配当前规则配置不兼容。
- 三条正确名称录制包 A1 a1_hair_wrap / A2 a2_disambiguate / A3 a3_receipt_channel 均重放成功；A3 OCR 实际全 unreadable，后续确认流程继续，不能证明真实自动识别。
- db-check 为 database=0003 / head=0003。
- 最终结论与分级处理要求写入 report.md；未修改业务实现或部署。

## 同步后最终状态
- 原 node_failed 部署阻断已解除，当前镜像与五个关键源码文件哈希一致；新图/引导/保留/告警模块均部署。
- 两项部署遗漏修复：真实 KB manifest 挂载；容器 retrieval config 显式路径。release.sh 变量中文标点解析也已修复。
- 真实 HTTP 六场景、真实五并发、浏览器操作与刷新恢复均通过，后端 434/434。
- 模型当前 DeepSeek / 智谱 ready，智谱最小调用已实测。仍无完整双厂商逐 task bake-off；真实图质量无验收素材。
- 未配置告警 sink；健康模型展示仍过粗；知识库使用 stub-embedding 版本；票32业务差异和冻结判定范围问题仍在。
