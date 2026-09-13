/** 观测台 HTTP 客户端。同源，无鉴权（黑客松范围）。 */
import type { CaseRow, Flow, Journey, Overview, SessionRow, Topology } from './types';

export class AdminError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value));
  }
  const url = query.size ? `/admin/api${path}?${query}` : `/admin/api${path}`;
  const res = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
  if (!res.ok) return fail(res);
  return res.json();
}

async function send<T>(path: string, method: 'POST' | 'PATCH', body: unknown): Promise<T> {
  const res = await fetch(`/admin/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) return fail(res);
  return res.json();
}

async function fail(res: Response): Promise<never> {
  let detail: { code?: string; message?: string } = {};
  try {
    const body = await res.json();
    detail = body?.detail ?? body ?? {};
  } catch {
    /* 非 JSON 错误体 */
  }
  throw new AdminError(res.status, detail.code ?? `http_${res.status}`, detail.message ?? res.statusText);
}

export type SessionFilters = {
  from?: string; to?: string; outcome?: string; reason?: string;
  category?: string; sku?: string; plan?: string; q?: string; cursor?: string; limit?: number;
};

export const api = {
  overview: (params: { from?: string; to?: string; bucket?: string; dim?: string }) =>
    get<Overview>('/metrics/overview', params),
  flow: (params: { from?: string; to?: string; category?: string; outcome?: string }) =>
    get<Flow>('/metrics/flow', params),
  topology: () => get<Topology>('/graph'),
  sessions: (params: SessionFilters) =>
    get<{ items: SessionRow[]; next_cursor: string | null }>('/sessions', params),
  journey: (id: string) => get<Journey>(`/sessions/${encodeURIComponent(id)}/journey`),
  cases: (params: { verdict?: string; status?: string; tag?: string }) =>
    get<{ items: CaseRow[]; tag_stats: { value: string; n: number }[]; reason_tags: string[] }>('/cases', params),
  labelCase: (body: { session_id: string; run_id?: string | null; verdict: string; reason_tags: string[]; note?: string; labeled_by?: string }) =>
    send<CaseRow>('/cases', 'POST', body),
  patchCase: (caseId: string, body: Record<string, unknown>) =>
    send<CaseRow>(`/cases/${encodeURIComponent(caseId)}`, 'PATCH', body),
};
