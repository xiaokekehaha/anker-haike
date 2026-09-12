# 02: 前端空壳与健康灯

**What to build:** Vite + React 19 + TypeScript 单页由编排服务托管，页面顶部 HeaderBar 轮询健康接口并用三色灯显示 llm / weknora / db 状态。用户打开首页就能看到系统是否可用。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** ready-for-agent

- [ ] 构建产物由编排服务静态托管，同源访问无 CORS 配置
- [ ] HeaderBar 每 10 s 刷新一次，组件不可用时灯变红并有文字提示
- [ ] CSS 变量 + CSS Modules，深浅色跟随系统
- [ ] 工程结构含 state / api / types / components / styles 目录骨架

**设计依据：** 05 §1、§3、§7
