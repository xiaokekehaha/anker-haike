# 补遗

## 2026-09-19 决策与落地记录

用户决策（`/goal`）：开始开发 P0 + P1；历史会话可以清理，不用考虑兼容。plan.md 保持原样，取舍记在此处。

### E1–E8 采用情况

| 编号 | 采用 | 说明 |
| --- | --- | --- |
| E1 | P0 + P1 | P2（source 列、queue join、导出、契约化）未做 |
| E2 | 默认首页 = 坐席工作台 `/desk` | `/` 重定向到 `/desk`；旧路径 `/approvals*` `/cases` **不做重定向**（用户明示不考虑兼容） |
| E3 | 复用聊天端 `Timeline` + `RecordPanel` | `Timeline` 加 `readOnly` prop；`SessionView` 用 `reducer(initialState, restore)` 把快照变成 `SessionState`；删除 `ReadonlyTimeline` 与手写 `TimelineItem` / `Snapshot` 类型 |
| E4 | 业务主口径按问题 | 看板第一行 L3 指标；会话口径的自助解决率 / 闭环率从 KPI 卡撤下，结局构成保留 |
| E5 | 五难点进本轮，缺数据的标「待接数据」 | 看图可用率无聚合查询，显示 —；其余四项用现有 overview / l3 数据 |
| E6 | UI 与前端类型改叫「复盘」 | `CaseRow` → `ReviewRow`，`api.cases/labelCase/patchCase` → `reviews/labelReview/patchReview`；表名与后端路径不动 |
| E7 | 契约化推后 | 仍手写类型，但快照类型改用生成的 `SessionSnapshot` |
| E8 | 前端按 remedy 枚举渲染，后端未放开的显示「后端暂未放开自动办理」并禁用批准 | `APPROVABLE = {replace}` 常量注明 D-SR-4 |

### 与 plan.md 的偏差

- **队列行的客户上下文**：`queue()` 未 join（P2），前端用 `/sessions?limit=100` 按 `session_id` 拼。真实库里的演示案件（`DEMO-*` 订单）的会话不在 analytics 事实表里，因此行内显示「（无会话摘要）/ 未识别」；P2 做 join 后自然补上。
- **五难点证据 tab** 的「情绪轨迹」在升级前显示「契约待扩」，与客户端 D2 的结论一致。
- 看板同时请求三次 overview（当前维度 / 原因 / 情绪）以拼五难点指标，回归测试断言次数为 3。
- `admin.css` 仍是全局类名，未改 CSS Modules；聊天端组件带自己的 CSS Modules 进入管理端包。
- 聊天端 `ToolRow` 顺带补了 `logistics.query` 等工具名的中文。

### 测试

- `admin/__tests__/pages.test.tsx` 改为 Board / Sessions，并 mock `l3Api`；断言看板三次取数、口径文字可见、模型降级率与检索无命中率。
- 全量前端：26 文件 222 用例通过。

### 验证

5174 dev 服务器（代理到本机 8000 真实库）1360 / 1100 px 走查：`/desk` 队列分组与 SLA 着色、`/desk/:id` 三栏（客户对话复用聊天端渲染、服务记录、判定表格中文标签、决定表单枚举化）、`/board` 三行口径、`/sessions` 新筛选与案件列、`/sessions/:id` 默认对话 + 五难点证据 tab、`/lab` 流程图 + 模型表 + 复盘库；无控制台错误。
