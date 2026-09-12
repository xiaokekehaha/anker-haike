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
    body = await res.json();
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

export async function getSnapshot(sessionId: string, signal?: AbortSignal): Promise<SessionSnapshot> {
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { signal, cache: 'no-store' });
  if (!res.ok) return fail(res);
  return res.json();
}

/** 发送文本 + 图片；返回 SSE 响应（调用方用 readSSE 消费）。 */
export async function sendMessage(sessionId: string, text: string, files: File[], purpose: 'fault' | 'receipt', signal?: AbortSignal): Promise<Response> {
  const form = new FormData();
  form.set('text', text);
  form.set('purpose', purpose);
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
