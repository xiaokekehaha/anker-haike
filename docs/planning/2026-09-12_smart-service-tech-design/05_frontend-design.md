# 前端组件设计（轻量 TypeScript Web UI）

## 1. 选型（2026-09-12 修订）

约束：Web UI、TypeScript、Vite 静态单页、后端 Python。

| 方案 | 适合情况 | 取舍 | 结论 |
| --- | --- | --- | --- |
| **Vite + React 19 + TypeScript** | 会持续演进的业务 Agent 界面，需要自由定制并复用 React 生态 | 运行时比 Preact 大约 40 KB gzip，对本项目不构成问题 | **采用** |
| Vite + Preact + Signals | 固定几类卡片的一次性演示，严格控体积 | 事件行为、Signals 用法、第三方 React 组件兼容性仍需逐个验证 | 备选，范围不扩展时可退回 |
| Vite + React + assistant-ui | 聊天是核心入口，需要工具调用展示、附件、历史会话 | 其 LangGraph 运行时要求 LangGraph Server API，现有 FastAPI 自定义 SSE 不能直接接，需要写自定义 runtime 适配 | 本期不接，作为演进路径 |
| React + CopilotKit | Agent 需读取页面状态、操作页面、与用户协作 | 有 Python LangGraph 接入与共享状态能力，但要接受其 AG-UI 协议与接入方式 | 本期不接，后续若需页面级协作再评估 |

修正说明（对早前版本的更正）：
- Preact 官网宣传约 3 KB，是运行时体积，不是应用体积；最终以实际构建产物为准。
- 「团队零学习成本」说法过满；Preact 的事件差异与 compat 层仍需验证。
- 选 React 不等于选 Next.js，Vite + React 同样可以产出静态文件部署。
- AI SDK UI 支持 React、Vue、Svelte 等多框架，早前「只绑定 React」判断不准确；本项目不用它的原因是其流协议与 Python 后端的自定义 SSE 不匹配，不是框架绑定。
- CopilotKit 有官方 Python LangGraph 接入，不应因后端是 Python 而排除。

配套：
- 构建：Vite，静态产物由 FastAPI 或 Nginx 托管。
- 状态：`useReducer` + Context 管理会话 timeline；不引入 Redux。若组件间共享状态变多，再加 zustand（约 1 KB）。
- 事件校验：zod 或 valibot，按 SSE 事件 Schema 解析，非法事件丢弃并打日志。
- 样式：CSS 变量 + CSS Modules，不引入 Tailwind 构建链路；深浅色跟随系统。
- 流式接收：`fetch` + `ReadableStream` 手写 SSE 解析，不用 `EventSource`（发消息需 POST 与 multipart）。
- Markdown：react-markdown + rehype-sanitize。
- 演进路径：聊天基础能力需求增多时，为 assistant-ui 写一个消费本项目 SSE 契约的自定义 runtime，业务卡片作为其 tool UI 注册；业务卡片组件本身不变。

## 2. 与后端的契约

事件、动作、快照的唯一定义在 08_session-execution-contract.md，前端类型由 `make contracts` 从后端 Schema 生成，本节只摘录形状供阅读，以生成文件为准。

前端判别联合类型（摘录）：

```ts
type ServerEvent = { seq: number; run_id: string } & (
  | { type: 'run_started'; resumed: boolean; deadline_ms: number }
  | { type: 'ping' }
  | { type: 'progress'; stage: Stage; substage?: string }
  | { type: 'tool_call'; tool_id: string; name: string; status: 'started' | 'finished' | 'failed'; summary?: string }
  | { type: 'message_start'; message_id: string; replaces?: string }
  | { type: 'message'; message_id: string; delta: string }
  | { type: 'message_end'; message_id: string; status: 'completed' | 'aborted'; model_tier?: 'primary' | 'fallback' }
  | { type: 'product_card'; card_id: string; version: number; candidates: ProductCandidate[] }   // candidate.in_scope
  | { type: 'step_card'; card_id: string; version: number; step: TroubleshootStep }             // step.evidence_ids
  | { type: 'evidence'; items: EvidenceItem[] }                                                   // item.evidence_id
  | { type: 'receipt_card'; card_id: string; version: number; fields: ReceiptFields; confidence: Record<string, number>; unreadable: string[] }
  | { type: 'awaiting_input'; kind: PendingKind; interrupt_id: string; card_id: string; version: number }
  | { type: 'escalation_summary'; card_id: string; summary: EscalationSummary }
  | { type: 'error'; code: string; message: string; recoverable: boolean; retry_with_same_action: boolean }
  | { type: 'done'; reason: 'completed' | 'awaiting_input' | 'error' | 'cancelled'; version: number }
);
type PendingKind = 'select_product' | 'step_feedback' | 'upload_receipt' | 'confirm_receipt';
type PendingInput = { kind: PendingKind; interrupt_id: string; card_id: string; version: number };  // 与 awaiting_input 同结构
```

前端会话状态机（比框架选择更重要，先定义清楚）：

| 前端状态 | 进入事件 | 允许的用户动作 |
| --- | --- | --- |
| idle | 会话创建 / done(completed) | 发消息 |
| streaming | run_started | 取消 |
| tool_running | tool_call(started) | 取消 |
| awaiting_input | awaiting_input | 点卡片按钮或按 kind 输入；「请求人工」始终可用。kind=upload_receipt：Composer 切换为凭证上传（purpose=receipt），可「跳过」；kind=confirm_receipt：ReceiptCard 字段可编辑，confidence < 0.7 标黄，提交 confirm_receipt 带 edited[]；kind=step_feedback 时 Composer 保留自由输入，提交即 rediagnose 并提示「将重新判断故障」 |
| failed | error(recoverable=false) / done(error) | 请求人工；recoverable 时按 retry_with_same_action 决定复用 action_id 重试或重新发送 |
| recovering | 页面加载、断流、超过 deadline+5 s | 先 GET 快照；active_run 未过期 → 续接 events?after_seq；否则按 pending_input 回到 awaiting_input 或 idle（08 §6） |

- awaiting_input 与 done(awaiting_input) 成对出现，前端据此把 card_id 对应卡片置为「待反馈」，其余禁用。
- 卡片事件按 card_id 幂等：重复到达时更新而非追加（interrupt 重跑会重发）。
- 消息按 message_id 聚合；收到 message_start.replaces 时替换旧消息内容，不拼接。
- 动作请求体：{action_id（前端 uuid，重试复用）, interrupt_id, card_id, expected_version, kind, payload}；409 时读取返回的快照并重建。
- 快照是权威，本地状态与之冲突时以快照为准。

契约文件由 `make contracts` 生成到 src/types/，CI 比对；fixture 位于 contracts/fixtures，前端 reducer 测试与后端流式测试共用。

## 3. 组件结构

```
App
├── HeaderBar            组件状态灯（llm / weknora / db），来自 /health
├── ProgressBar          五阶段进度，监听 progress
├── ChatPane             消息列表，按 timeline 渲染
│   ├── UserBubble       文本 + 图片缩略图
│   ├── AssistantBubble  流式文本（marked 渲染）
│   ├── ProductCard      候选产品按钮组（in_scope=false 标「本期不支持」）→ select_product
│   ├── StepCard         步骤标题、操作、预期结果、caution、来源角标 → step_feedback
│   ├── ReceiptCard      OCR 字段可编辑，低置信标黄，「确认」/「跳过」→ confirm_receipt / skip_receipt
│   ├── EvidenceDrawer   可折叠来源片段列表，按 evidence_id 与 StepCard 联动高亮
│   └── SummaryCard      结构化摘要（summary 对象），含 receipt.status 与 next_step，一键复制
├── Composer             文本框、图片选择（purpose=fault / receipt，压缩至 1600px）、发送、请求人工、取消
└── Toast                error 事件提示
```

约 11 个组件。卡片组件是预注册的固定 React 组件，模型只决定「发哪种卡、填什么字段」，不生成 UI 描述。未来接 assistant-ui 时，这些卡片以 tool UI 形式注册，逻辑不变。

## 4. 状态模型（useReducer）

```ts
type SessionState = {
  id: string | null;
  stage: Stage;
  ui: 'idle' | 'streaming' | 'tool_running' | 'awaiting_input' | 'failed' | 'recovering';
  version: number;
  activeRun?: { run_id: string; deadline_at: string };
  pendingInput?: PendingInput;   // 与 awaiting_input 事件同结构
  timeline: TimelineItem[];   // 用户消息、助手消息、卡片、工具调用行，按时间顺序
  health: Health;
};
type Action = { type: 'server_event'; event: ServerEvent } | { type: 'user_send'; ... } | { type: 'action_sent'; action_id: string } | { type: 'restore'; snapshot: SessionSnapshot };
```

- reducer 把每个 ServerEvent 映射为 timeline 变更与 ui 状态迁移，纯函数可单元测试。
- 卡片用户点击后进入 disabled 并显示所选项，保留历史。
- session_id 存 sessionStorage，刷新后 dispatch restore。

## 5. 流式接收实现要点

```ts
async function stream(url: string, body: FormData, onEvent: (e: ServerEvent) => void) {
  const res = await fetch(url, { method: 'POST', body });
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const data = raw.split('\n').filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('');
      if (data) onEvent(parseServerEvent(JSON.parse(data)));
    }
  }
}
```

- 心跳：每 5 s 收到 ping；15 s 无事件提示「仍在处理」；超过 run_started.deadline_ms + 5 s 视为断流。
- 断流：进入 recovering，先 GET 快照；active_run 仍在 → 续接 `events?after_seq=最后 seq`；否则按快照回到相应状态。不自动重放输入。

## 6. 交互细节

- 情绪为焦急或愤怒时，助手第一句安抚先流式出现，卡片随后到达，避免用户先看到冷冰冰的卡片。
- StepCard 同时只允许一个处于「待反馈」状态；旧卡片折叠为一行。
- ProgressBar 的阶段跳转带 300 ms 过渡，让评委能看见流程推进。
- 图片上传失败或超 5 MB 在 Composer 内联提示，不进入对话流。
- 演示模式开关（URL 参数 `?replay=1`）：前端不变，后端切回放适配器。
- 取消：streaming 或 tool_running 时调用 POST /cancel，随后 abort fetch；仅 abort 不等于取消，run 会继续到完成或 deadline。
- 请求人工：任何状态可点，服务端忽略 version / pending 校验并取消 active run。

## 7. 工程结构

```
frontend/
├── index.html
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── state/      reducer.ts, types.ts
│   ├── api/        sse.ts, client.ts
│   ├── types/      events.ts（由 schema 生成）
│   ├── components/ 上述组件
│   └── styles/     tokens.css, base.css
└── package.json    react, react-dom, zod, react-markdown, rehype-sanitize
```

运行时依赖 5 个，构建产物以实际 `vite build` 报告为准，预期 gzip 100 KB 量级。

## 来源
- https://preactjs.com/guide/v10/differences-to-react/
- https://www.assistant-ui.com/docs/runtimes/langgraph/overview
- https://docs.copilotkit.ai/langgraph-python/quickstart
- https://ai-sdk.dev/docs/ai-sdk-ui/overview
- https://dev.to/eugenioenko/the-lightweight-javascript-framework-renaissance-of-2026-4ee0
- https://theartofcto.com/technologies/compare/preact/svelte
- https://www.pkgpulse.com/guides/lit-vs-svelte-2026
- https://dev.to/alexander_lukashov/i-evaluated-every-ai-chat-ui-library-in-2026-heres-what-i-found-and-what-i-built-4p10
- https://focused.io/lab/streaming-agent-state-with-langgraph
- https://dev.to/kasi_viswanath/streaming-ai-agent-with-fastapi-langgraph-2025-26-guide-1nkn
