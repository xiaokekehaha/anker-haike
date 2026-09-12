# 前端空壳与健康灯（票 02）

Vite + React 19 + TypeScript；使用 CSS Modules 和主题变量，跟随系统深浅色。当前只提供首页与健康监测，对话接入在后续票据中实现。

## 构建与同源访问

需要 Node.js 22.12+（22 / 24 / 26 系列），依赖通过 package-lock.json 锁定。

在仓库根目录执行：

```bash
npm --prefix frontend ci
npm --prefix frontend run build
make dev-api
```

打开 http://localhost:8000。构建产物为 `frontend/dist/`，现有 FastAPI `STATIC_DIR` 默认指向该目录。需要先构建再启动后端（或构建后重启），因为静态目录在创建应用时挂载。请求使用同源 `/health`，不配置 CORS。

Docker 的 `orchestrator/Dockerfile` 使用 Node 构建阶段，再将产物复制到 Python 镜像的 `/srv/static`。从仓库根目录 `make up` 即可触发，不要求宿主机预先构建前端。

## 开发与验证

```bash
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run build
```

开发页为 http://localhost:5173，Vite 将 `/health` 代理到本机 8000 端口。后端端口改变时同步修改 `vite.config.ts` 中的代理地址。`vite preview` 只预览静态产物；验证真实健康灯请使用 FastAPI 同源入口或开发代理。

## 健康状态

- 首次加载立即请求，此后每 10 秒刷新，单次请求 5 秒超时；可手动重新检查。
- 绿灯：可用；黄灯：检查中或未配置；红灯：不可用或连接异常。文字与颜色同时呈现。
- 模型状态读取 `components.models[lane]`，绿色表示配置已就绪，不代表远程推理调用已验证。
- `/health` 的 HTTP 503 仍解析逐组件快照；超时、网络错误、非法 JSON 或不兼容响应清除旧状态，避免残留绿灯。
- 后端 `detail`、连接信息不进入 UI 状态或日志。

## 目录边界

`src/state` 管理健康轮询；`src/api` 请求和校验健康响应；`src/types` 为健康类型；`src/components` 为 HeaderBar；`src/styles` 为系统主题和全局样式。票 04 后续生成的事件类型与票 06 reducer / SSE 解析不在本票实现范围。
