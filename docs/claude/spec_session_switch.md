# Spec：新建会话与本机最近会话切换（第一阶段，前端 only）

日期：2026-09-13　分支：feat/smart-service-impl　范围：frontend/

## 背景
- 前端只在 `sessionStorage['haike.session_id']` 存一个会话 id，按标签页隔离；`useSession.reset()` 存在但没有任何按钮调用。
- 后端没有会话列表接口、没有用户身份；session_id 是唯一凭据。测试时同一标签页永远看到同一个旧会话，既不能新建也不能切换。
- 后端保留策略（票 48）：会话 24 h（`RETENTION_SESSION_HOURS`，按 `sessions.updated_at`，有 active run 不删），图片 1 h，追踪 7 d。过期后 `GET /sessions/{id}` 返 404。

## 目标
1. 页面上可以「新建会话」。
2. 同一浏览器内可以在本机最近用过的会话之间来回切换，切回去后时间线 / 阶段 / 待输入卡片完整恢复。
3. 不改后端。所有恢复逻辑复用现有 `restore`（快照 + active run 重放）。

## 设计

### 存储
| 键 | 位置 | 内容 | 作用域 |
| --- | --- | --- | --- |
| `haike.session_id` | sessionStorage（不变） | 当前会话 id | 每标签页 |
| `haike.recent_sessions` | localStorage（新增） | `RecentSession[]`，最多 20 条，按 `updated_at` 倒序 | 整个浏览器 |

```ts
type RecentSession = { id: string; created_at: string; updated_at: string; title: string | null; stage: Stage | null };
```
- 标题 = 首条用户消息前 30 字；没有用户消息时显示「新会话 · 时间」。
- 保留当前标签页用 sessionStorage 的原因：新标签页 = 新会话的隔离语义不变；localStorage 的列表只是「可切换的候选」。
- 列表维护时机（全在 `useSession` 内）：
  - 创建成功（`POST /sessions`）→ 加入列表。
  - 每次 `user_send` → 刷新 `updated_at`，首次补 `title`。
  - 每次 `restore` 成功 → 刷新 `stage`、`updated_at`，`title` 为空时从快照时间线首条 `user_message` 补。
  - 快照 404 → 从列表移除（后端已过期或被删除）。
  - 读取时丢弃 `updated_at` 超过 48 h 的条目（后端默认 24 h 过期，留一倍余量避免配置不一致时误删；最终以 404 为准）。
- 跨标签页同步：`useSyncExternalStore` 监听 `storage` 事件 + 本页写入后派发自定义事件。

### 交互（`SessionSwitcher` 组件，放在工作区标题栏右侧）
- **会话下拉**（原生 `<select>`，aria-label「切换会话」）：列出最近会话，当前会话选中；没有任何记录时不渲染下拉。选项文案 `标题 · 阶段标签`，阶段标签复用 ProgressBar 的五段文案。
- **新建会话** 按钮：
  - 当前空白会话（`id === null`）→ 禁用。
  - 正在运行（streaming / tool_running / recovering）或有待输入卡片 → `window.confirm('当前排查会中断，确定开始新会话？')`；确认后若有 active run 先 `POST /cancel`，再 reset。
  - 其余情况直接 reset。reset 只清 sessionStorage 与内存状态，旧会话仍留在最近列表里可切回。
- **切换**：
  - 选到当前会话 → 无操作。
  - 否则中止本页正在进行的请求（不取消服务端 run，run 会自己跑完并落库，切回来靠快照 + 重放看到结果），写入 sessionStorage，走 `restore`。404 → 移出列表并 reset，Toast 提示「该会话已过期」。
  - 切换过程中下拉与新建按钮禁用。

### 已知限制（写进手册）
- 只是「本机最近」，换浏览器 / 清站点数据就没有；跨设备与客服查看是第二阶段（owner_id + 列表接口）。
- 图片 1 h 过期：切回超过 1 h 的会话，用户上传的照片会加载失败，文字与卡片完整。
- 24 h 后会话在服务端删除，列表里的条目会在切换时以 404 清除。

## 改动
| 文件 | 说明 |
| --- | --- |
| `src/state/recentSessions.ts`（新） | localStorage 读写、裁剪、`useRecentSessions()` |
| `src/state/useSession.ts` | 维护最近列表；新增 `switchTo(id)`、`startNew()`；导出 `recent` |
| `src/components/SessionSwitcher.tsx` + `.module.css`（新） | 下拉 + 新建按钮 |
| `src/App.tsx` | 工作区标题栏挂载 SessionSwitcher |
| 测试 | `recentSessions.test.ts`、`useSession.test.tsx` 增切换 / 新建 / 404 用例、`SessionSwitcher.test.tsx` |
| `docs/claude/spec_manual_test_guide.md` | 补手工验证步骤 |

## 不做
- 不加后端接口、不加 owner 身份、不改 TTL。
- 不做会话重命名 / 删除（删除需要 admin token，属运维动作）。

## 验证
- `npm run typecheck`、`npm test`、`npm run build`。
- 浏览器：发一条消息 → 新建会话 → 再发一条 → 下拉切回第一条，时间线与阶段恢复；刷新页面后当前会话与下拉列表都保留；开新标签页是空白会话但下拉里能看到两条。
