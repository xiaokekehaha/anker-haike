/** 编排服务 HTTP 客户端（08 §4 / §6 / §7；03 §2.1）。同源，无 CORS。 */
import type { ActionRequest } from '../types/actions';
import type { SessionSnapshot } from '../types/snapshot';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public snapshot?: SessionSnapshot) {
    super(message);
  }
}

async function fail(res: Response): Promise<never> {
  let body: { code?: string; message?: string; snapshot?: SessionSnapshot } = {};
  try {
    const raw = await res.json();
    body = raw.detail ?? raw;
  } catch {
    /* 非 JSON 错误体 */
  }
  throw new ApiError(res.status, body.code ?? `http_${res.status}`, body.message ?? res.statusText, body.snapshot);
}

export async function createSession(signal?: AbortSignal): Promise<{ session_id: string; version: number }> {
  const res = await fetch('/sessions', { method: 'POST', signal });
  if (!res.ok) return fail(res);
  return res.json();
}

/** 「确定不存在」只认后端显式的 session_not_found；FastAPI 的路由级 404（部署错 / 版本回退）
 *  会 fallback 成 http_404，不能当成会话过期，否则一次错误发布就会清空本机最近列表。 */
export function isMissingSession(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404 && error.code === 'session_not_found';
}

/** 批量存活探测；只有请求本身成功才返回结果，调用方据此决定是否动本地列表。 */
export async function probeSessions(sessionIds: string[], signal?: AbortSignal): Promise<string[]> {
  const res = await fetch('/sessions/_exists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_ids: sessionIds }),
    signal,
    cache: 'no-store',
  });
  if (!res.ok) return fail(res);
  const body: unknown = await res.json();
  // 形状不对（例如代理把 SPA 回退当成了响应）一律当作探测失败。
  if (!body || typeof body !== 'object' || !Array.isArray((body as { alive?: unknown }).alive)) {
    throw new ApiError(res.status, 'bad_probe_response', '存活探测返回了预期外的内容');
  }
  return (body as { alive: unknown[] }).alive.filter((id): id is string => typeof id === 'string');
}

export async function getSnapshot(sessionId: string, signal?: AbortSignal): Promise<SessionSnapshot> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { signal, cache: 'no-store' });
  if (!res.ok) return fail(res);
  return res.json();
}

/** 发送文本 + 图片；返回 SSE 响应（调用方用 readSSE 消费）。 */
export async function sendMessage(sessionId: string, text: string, files: File[], purpose: 'fault' | 'receipt', inputId: string, expectedVersion: number, signal?: AbortSignal): Promise<Response> {
  const form = new FormData();
  form.set('text', text);
  form.set('purpose', purpose);
  form.set('input_id', inputId);
  form.set('expected_version', String(expectedVersion));
  for (const f of files) form.append('images', f, f.name);
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/messages`, { method: 'POST', body: form, signal });
  if (!res.ok) return fail(res);
  return res;
}

export async function postAction(sessionId: string, action: ActionRequest, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/actions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(action),
    signal,
  });
  if (!res.ok) return fail(res);
  return res;
}

export async function resumeEvents(sessionId: string, runId: string, afterSeq: number, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/events?after_seq=${afterSeq}`, { signal });
  if (!res.ok) return fail(res);
  return res;
}

export async function cancelRun(sessionId: string, runId: string, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId }),
    signal,
  });
  if (!res.ok && res.status !== 409) return fail(res);
}

export function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
