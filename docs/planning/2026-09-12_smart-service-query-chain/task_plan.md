# 意图、查询改写与召回的最小补齐

## Goal
核对现有架构与开发票，按奥卡姆剃刀原则补齐理解到卡片的责任边界、必要契约和验收落点。

## Phases
### Phase 1: 核对设计和实现
**Status:** complete

### Phase 2: 最小文档与需求补充
**Status:** complete

### Phase 3: 一致性检查并说明开发顺序
**Status:** complete

### Phase 4: 无命中改写与澄清纠错补充
**Status:** complete

### Phase 5: 跨文档与开发验收复核
**Status:** complete

## Decisions
- 优先复用 intake、diagnose、KnowledgeAdapter 和现有事件协议。
- 本轮产出设计与可执行需求；已有未提交实现改动作为只读证据，避免干扰正在进行的开发。
- 遵守数据库只查询约束；本轮无需访问数据库。
- 查询规范化放在现有 retrieval_query 函数；上下文处理复用 intake；召回/重排复用 KnowledgeAdapter/WeKnora。
- 首轮补入现有未完成票 32、37，不重开已完成的 17/27，不新增服务、模型任务、卡片、事件或开发票。
- 用户追加：纳入默认关闭、只在真实 no_match 时触发的一次模型改写；复用 ModelRouter，明确与图片补检索共享的次数和预算边界。
- 用户追加：路由允许继续 / 澄清 / 升级三种处理结果；完善动作错误、语义不明、用户纠正与反复不明的验收。
- 可选改写与读图共享一次补检索名额；run 剩余至少 8 s 才启动 3 s invoke + 3 s 检索，至少留 2 s 收尾，默认关闭。
- R7 扩展为 product / symptom / conflict 的必要信息不明；连续两次澄清答复后才升级，内部 clarification 状态跨 run 保留。

## Errors Encountered
- 初次文件枚举包含不存在的 .openai 路径，rg 退出码为 2；已改用仓库文件枚举和明确存在的 docs 路径。
- 枚举了不存在的 orchestrator/app/contracts，rg 退出码为 2；已定位契约在仓库根 contracts/。
- 批量读取长文档出现输出截断；后续改按相关章节小范围读取。
- 追加阶段枚举了不存在的 sessions/actions.py，以及无匹配的 scripts/* glob；改从已知 contracts/actions.py 与文档核对，不再依赖该路径。
- 追加阶段依赖校验发现票 37/45 未覆盖票 23 的前端冲突恢复验收；已在 37 补显式依赖 23，并同步 README 表和图，45 经 37 继承。

## Next Step
追加设计与需求完善已完成。实现时按票 24/23 补澄清与动作边界，票 32/33 补可选改写与降级，票 37 集成多轮纠错，票 45 汇总验收；改写开关保持关闭直至金标和延迟验证达标。
