# WeKnora 第 26 项使用说明

## Goal
核实项目当前状态与锁定版本 WeKnora v0.8.0 的界面、tenant、导入、切片、Embedding 和检索流程，回答使用方式。

## Phases
1. 核实本地票面、部署及接入现状 — complete
2. 核对官方 v0.8.0 文档及源码 — complete
3. 整理带来源的使用说明与待实现差异 — complete
4. 补充可访问的页面链接与操作步骤，启动管理 UI — complete
5. 复核现有代码，解释选用原因、实际功能与未使用能力 — complete
6. 解释文件类型、可视化分块操作与多路检索融合/重排机制 — complete
7. 核对 Embedding 当前模型、云端调用计费与跨模型兼容边界 — complete
8. 推荐轻量本地 Embedding，解释本地检索配远程回答的部署方式 — complete

## Next Step
本地模型建议已完成，交付方案说明；没有安装、下载或迁移操作。

## Constraints
- 数据库只读；不执行知识导入。后续使用说明轮次仅启动可选 weknora-ui，未重建后端依赖。
- 区分已实现、框架能力和项目设计目标。
- 早期官方调研曾由后台代理执行；本轮直接核对代码与固定版本官方文档。

## Errors Encountered
- 本轮宽范围检索及部分批量输出被截断，后续按知识模块、会话节点和上游函数缩小读取范围，取得结论所需证据。
- planning-with-files 首次输出截断，已补读中间部分；执行核心规则已读取。
- 搜索不存在的根目录 scripts 导致 rg 返回 2，后续单独执行 compose 状态检查；项目目录清单已获取。
- UI 探测连接失败（curl 7），由 UI profile 尚未启动解释，无需重试。
- 后续查询 Settings.vue 初次路径错误，按 router 中组件路径改为 frontend/src/views/settings/Settings.vue 后读取成功。
