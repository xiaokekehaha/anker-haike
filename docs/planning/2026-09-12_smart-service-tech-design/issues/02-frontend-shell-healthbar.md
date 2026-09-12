# 02: 前端空壳与健康灯

**What to build:** Vite + React 19 + TypeScript 单页由编排服务托管，页面顶部 HeaderBar 轮询健康接口并用三色灯显示 llm / weknora / db 状态。用户打开首页就能看到系统是否可用。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done

**Owner:** Codex（2026-09-12 认领；本轮仅此一票）

**协作边界：** Codex 负责 `frontend/`、前端静态托管所需的最小接入及其验证；Claude Code 继续票 01 与其他未认领票。实施记录见 `../../2026-09-12_smart-service-frontend-shell/`。

- [x] 构建产物由编排服务静态托管，同源访问无 CORS 配置
- [x] HeaderBar 每 10 s 刷新一次，组件不可用时灯变红并有文字提示
- [x] CSS 变量 + CSS Modules，深浅色跟随系统
- [x] 工程结构含 state / api / types / components / styles 目录骨架

**验收记录（2026-09-12，Codex）：** 14 项前端测试通过；TypeScript 检查与 Vite 生产构建通过；使用现有 FastAPI 验证首页、JS / CSS / favicon 同源访问、API 路由优先和资源 404；浏览器验证手动刷新、真实故障状态及 390px 页面无横向溢出。后端现有 6 项测试及 ruff 通过。模型灯按当前 lane 显示配置状态；503 保留逐组件状态，断网或超时清除旧快照。深浅色由 prefers-color-scheme 媒体查询和 CSS 变量实现。

**集成说明：** 复用已有 FastAPI 静态挂载，仅在 orchestrator/Dockerfile 增加前端构建阶段。本机无 Docker，镜像构建与 Compose 启动待有 Docker 的环境验证（沿用票 01 的环境限制）。启动和目录说明见 [frontend/README.md](../../../../frontend/README.md)。

**设计依据：** 05 §1、§3、§7
