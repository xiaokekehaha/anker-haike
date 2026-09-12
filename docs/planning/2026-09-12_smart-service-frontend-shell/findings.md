# 发现

- Claude 的实施计划当前票 01 in_progress；票 02 尚未开始，已登记 Codex 认领。
- 后端已有 GET /health，响应含 status、lane、components.db / redis / weknora / models；models 按 domestic / overseas 通道给状态。
- 健康组件状态为 ok / down / unconfigured；db 不可用时 HTTP 503 仍返回完整 JSON。前端需保留该响应里的逐组件状态。
- 模型健康目前表示配置状态，不证明远程模型调用成功；页面需准确表达。
- 本机无 Docker，容器集成验证需在具备 Docker 的环境执行。
- FastAPI 已将存在的 STATIC_DIR 挂载在 API 路由之后，无需修改入口或配置；Dockerfile 原来依赖宿主 dist，已增量替换为 Node 构建阶段。
- 依赖核对：npm registry 的 React 19.3.0、Vite 8.3.0、@vitejs/plugin-react 6.1.1、Vitest 5.0.0；已锁定直接依赖和 package-lock.json。
- 官方参考：Vite https://vite.dev/guide/（Node 要求与构建）；React https://react.dev/reference/react/useEffect（轮询清理与 StrictMode 生命周期）。
