# WeKnora 第 26 项使用说明

## Goal
核实项目当前状态与锁定版本 WeKnora v0.8.0 的界面、tenant、导入、切片、Embedding 和检索流程，回答使用方式。

## Phases
1. 核实本地票面、部署及接入现状 — complete
2. 核对官方 v0.8.0 文档及源码 — complete
3. 整理带来源的使用说明与待实现差异 — complete
4. 补充可访问的页面链接与操作步骤，启动管理 UI — complete

## Next Step
管理 UI 已启动并通过 HTTP 检查，交付页面链接和使用步骤；第 26 项数据入库仍保持待实现状态。

## Constraints
- 数据库只读；不执行知识导入。后续使用说明轮次仅启动可选 weknora-ui，未重建后端依赖。
- 区分已实现、框架能力和项目设计目标。
- 官方调研由 research 技能要求的后台代理执行。

## Errors Encountered
- planning-with-files 首次输出截断，已补读中间部分；执行核心规则已读取。
- 搜索不存在的根目录 scripts 导致 rg 返回 2，后续单独执行 compose 状态检查；项目目录清单已获取。
- UI 探测连接失败（curl 7），由 UI profile 尚未启动解释，无需重试。
- 后续查询 Settings.vue 初次路径错误，按 router 中组件路径改为 frontend/src/views/settings/Settings.vue 后读取成功。
