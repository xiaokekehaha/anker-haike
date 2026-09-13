# 智能售后前端

Vite + React 19 + TypeScript；使用 CSS Modules 和主题变量，跟随系统深浅色。提供售后对话、组件健康状态和模型连通性列表。

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

开发页为 http://localhost:5173，Vite 将 `/health`、`/sessions`、`/models` 代理到本机 8000 端口。后端端口改变时同步修改 `vite.config.ts` 中的代理地址。`vite preview` 只预览静态产物；验证真实接口请使用 FastAPI 同源入口或开发代理。

## 健康状态

- 首次加载立即请求，此后每 10 秒刷新，单次请求 5 秒超时；可手动重新检查。
- 绿灯：可用；黄灯：检查中或未配置；红灯：不可用或连接异常。文字与颜色同时呈现。
- 顶部知识库、数据库使用健康灯；模型使用独立的可点击入口，不再将通道配置不全显示为用户页面的服务不可用。
- `/health` 的 HTTP 503 仍解析逐组件快照；超时、网络错误、非法 JSON 或不兼容响应清除旧状态，避免残留绿灯。
- 后端 `detail`、连接信息不进入 UI 状态或日志。

## 模型连通性

- 点击顶部「模型」打开弹窗，`GET /models/status` 仅读取运行时配置和最近结果，不调用模型。
- 当前通道包含其备用链引用的聊天模型（含跨通道备用）；其他聊天模型折叠展示。embedding/rerank 不参与本次基础对话检测。
- 「检测已配置模型」仅检测当前通道，缺密钥/模型 ID 的跳过；其他模型可以展开后逐项检测。
- `POST /models/{alias}/probe` 直连指定模型，发送简短文本，输出上限 16 token，最多 20 秒，不重试、不走业务备用链。同时最多 2 个探测；重复请求共享正在进行的同一探测。
- 已连通只表示该次基础文本调用返回了文本，不验证图片识别、结构化输出或整条业务链路。
- 状态包括未配置、未检测、检测中、已连通、连接失败。显示耗时、检测时间和固定的脱敏失败原因。接口请求失败显示「未能获取检测结果」，不把网络未知当厂商失败。
- 结果在进程内缓存 5 分钟，过期恢复「未检测」，重启清空。打开弹窗不会自动重测；若重新打开时检测仍在运行，只轮询其结果。
- 关闭弹窗停止排队中的检测；已发出的后端探测有时限并可供重新打开后查看。回放或关闭真实模型的环境禁止真实探测。

## 目录边界

`src/state` 管理健康轮询；`src/api` 请求、健康校验与事件校验；`src/types` 为健康及生成的契约类型；`src/components` 为 HeaderBar；`src/styles` 为系统主题和全局样式。会话 reducer / SSE 解析由票 06 接入。

## 契约生成与 CI（票 04）

唯一来源为 `contracts/haike_contracts/` 中的 Python 模型，导出到 `contracts/schema/`。安装前端依赖后，从仓库根目录执行：

```bash
make contracts                 # Python → JSON Schema → TypeScript / Zod
make contracts-check           # 只检查，不覆盖生成产物；漂移时非零退出
npm --prefix frontend test
npm --prefix frontend run test:codegen
uv run --project contracts python frontend/scripts/validate-fixtures.py
```

生成文件：`src/types/events.ts`、`actions.ts`、`snapshot.ts` 和 `src/api/events-schema.ts`。生成器保留动作响应 `ActionResult` / `ActionConflict`，并导出 `PendingKind` / `ActionKind` / `TimelineItem`，供后续 reducer 使用。生成文件禁止手改；SHA-256 注释也会让仅修改数值范围等无法用 TypeScript 表达的约束触发检查。

只重建前端产物可运行 `npm --prefix frontend run contracts:generate`；只检查前端漂移运行 `npm --prefix frontend run contracts:check`，后者打印统一格式差异，缺失文件同样失败。

`parseServerEvent(value: unknown): ServerEvent | null` 接收已解码的事件对象。它通过从相同 Schema 构建的 Zod 校验器验证；非法事件返回 null，后续 SSE 消费方应跳过。日志只包含固定错误码与问题数，不记录消息、凭证、未知字段名或完整验证错误。Zod 的 fromJSONSchema 是实验 API，版本已锁定，并在生成阶段验证兼容性；升级须通过协议样本与边界回归。

共享样本位于 `contracts/fixtures/`；`a1.json` 当前是空占位，不表示 A1 业务链路已完成。`events.valid.json` 的 15 种事件由前端 Zod 与后端 Pydantic 共同验证。

`.github/workflows/contracts.yml` 重新导出 Python Schema 并打印 git diff，随后检查前端产物、共享样本、单元测试与构建。所有操作仅作用于代码和 fixture，不访问数据库或模型服务。
