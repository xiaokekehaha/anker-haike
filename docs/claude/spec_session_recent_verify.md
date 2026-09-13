# spec：最近会话列表的存活校验

## 背景

会话切换下拉框的数据来自 localStorage `haike.recent_sessions`（`frontend/src/state/recentSessions.ts`），
纯本机、最多 20 条、按 `updated_at` 保留 48 h。后端 `sessions` 的保留期是 24 h
（`RETENTION_SESSION_HOURS`，`orchestrator/app/retention.py`），前端有意留了一倍余量，
注释写的是「最终以快照 404 为准」——也就是**懒惰失效**：只有用户点进某条、`restore` 拿到 404
才会 `removeRecent` 移除那一条。

结果是列表里长期躺着大量后端已删的死条目，开发期尤其明显。

## 目标

首屏加载时一次性校验列表里所有会话的后端存活状态，把确认不存在的从可见列表中剔除，
且**在任何服务端异常下都不能误删**。

## 误删风险盘点

| 故障 | 实际响应 | 只看 `status === 404` |
|---|---|---|
| 后端进程挂 | proxy 502/500，或 fetch 抛 TypeError | 不删 ✅ |
| 代理未配 / 路径前缀变更 | vite SPA 回退 200 + HTML，`res.json()` 抛 SyntaxError | 不删 ✅ |
| 路由挂载错误 / 版本回退 | FastAPI 默认 404，体为 `{"detail":"Not Found"}` | **误删，且全量** ⚠️ |
| DB 连到空库 / migration 重置 | 合法的 `session_not_found` | **误删** ⚠️ |
| DB 挂 | `store.session_exists` 抛异常 → 500 | 不删 ✅ |
| 请求超时 / 中断 | AbortError | 不删 ✅ |

现状 `useSession.open()` 只判断 `error.status === 404`，第 3 行场景今天即会触发全量误删。

## 设计：三层防护

### 1. 认错误码，不认状态码

「确定不存在」= `status === 404` **且** `code === 'session_not_found'`。
后端真正的会话缺失走 `HTTPException(404, detail={"code": "session_not_found", ...})`
（`orchestrator/app/sessions/router.py:443`），FastAPI 的路由级 404 没有这个 code
（客户端 `fail()` 会 fallback 成 `http_404`），二者天然可区分。

### 2. 批量探针，只信 200

新增 `POST /sessions/_exists`：

- 入参 `{"session_ids": [...]}`（上限 50，超出 422）
- 出参 `{"alive": [...]}`，只回存在的 id
- 实现只调 `store.session_exists`，**不加会话锁、不 reconcile、不派生快照**

之所以不复用 `GET /sessions/{id}`：那条路由要 `session_lock.hold` + `reconcile_session` +
`_consistent_snapshot`，首屏并发 20 个重请求不可接受。

探针请求本身成为健康门闩——后端挂 / 路由不存在 / DB 挂全都返回非 200 或不可解析的体，
此时**整轮跳过，不动任何本地数据**。

路由注册在 `/{session_id}` 系列之前；`_exists` 与现有 POST 路由无冲突
（不存在 `POST /{session_id}`）。

### 3. 标记而非删除

`RecentSession` 增加可选字段 `missing_since: string | null`。

- 确认缺失 → `markMissing(ids)` 写入时间戳，**不从 localStorage 移除**
- 可见列表（`listRecent` / `useRecentSessions`）过滤掉带标记的条目
- 探针确认存在 → `markAlive(ids)` 清除标记，会话自动回到列表
- 物理删除仍由既有的 48 h `updated_at` 过期负责

这样即便「连到空库」这种探针也识别不了的场景发生，误判也是可逆的：
后端恢复后下一轮探测就把会话找回来。

## 改动清单

- `orchestrator/app/sessions/router.py`：新增 `POST /sessions/_exists`
- `frontend/src/api/client.ts`：新增 `probeSessions(ids, signal)`；新增 `isMissingSession(error)` 判定
- `frontend/src/state/recentSessions.ts`：`missing_since` 字段、`readAll` / `listRecent` 分离、
  `markMissing` / `markAlive`
- `frontend/src/state/useSession.ts`：挂载时跑一次 `verifyRecent()`；`open()` 的 404 分支
  改用 `isMissingSession` + `markMissing`
- 测试：`recentSessions.test.ts` 补标记语义；`useSession.test.tsx` 补「探针失败不动列表」
  与「路由级 404 不删」；后端补 `_exists` 路由测试

## 不做

- 跨设备同步会话列表（仍是本机 localStorage，属第二阶段）
- 定时轮询校验；只在挂载时跑一次，够用且不增加常驻请求
