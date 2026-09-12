# 发现

- 接手 HEAD 9413c3f，存在大量未提交前后端实现；保留已有工作。
- 会话、模型、检索、视觉、凭证识别、部署基础能力已有；34–36 claimed 且 guide 正在补齐，接续原分工前端线。
- 主计划滞后于票面及代码；前端组件齐全，但 useSession 没有异步恢复测试。
- reducer 缺少 seq 去重；快照叠加历史 delta 可重复回复。
- reset/unmount 未阻止旧请求回写；consume finally 依赖尚未刷新的 React state。
- 409 只 restore 未续接 active run；服务端明确允许的同 action_id 重试缺失。
- 用户授权本项目数据库增删改查，已同步 AGENTS.md 和 CLAUDE.md；其他数据库只查询。
