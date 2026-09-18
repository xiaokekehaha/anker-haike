# 任务流水

## Goal
完成 WeKnora 源码与本地案例的 RAG 数据流、架构分析。

## Phases
- [x] 1. 运行版本与案例确认（complete）
- [x] 2. 固定版本源码追踪（complete）
- [x] 3. 案例映射与接入对照（complete）
- [x] 4. 文档交付与证据核对（complete）
- [x] 5. 评估链路B的改写、召回、排序与现有评测（complete）
- [x] 6. 提出按必要性排序的修改方案（complete）

## Next Step
链路B修改必要性分析已完成；交付chain-b-recommendations.md及运行/评测证据。本轮不实施业务改造。

## Errors Encountered
- 初次批量读取结果过大，后续按文件拆分并限制定位输出。
- 浏览器未登录，改用本地只读 PostgreSQL 和容器日志；未读取浏览器凭据。
- 两次定位命令假定不存在的路径或通配符，后续用 rg --files 确认路径。
- 一次文档补丁因未包含行尾链接匹配失败；改为精确匹配后应用，未影响业务代码。
