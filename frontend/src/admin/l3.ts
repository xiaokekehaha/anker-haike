import type { GateResult, PolicyDecision, ProposalOption } from '../types/events';
import type { Snapshot } from './types';

export type ServiceCase = {
  case_id: string; session_id: string; issue_id: string; status: string; priority: string; complaint_risk: boolean;
  revision: number; opened_at: string; updated_at: string; owner: string | null;
  policy_decision: PolicyDecision | null; gate_result: GateResult | null;
  proposal: { options: ProposalOption[]; chosen_option_id?: string | null } | null;
  external_refs: Record<string, string>; snapshot?: Snapshot | null;
  decisions?: { decision_id: string; decision: string; note: string; override_reason: string | null; consumed_input_id: string | null }[];
  events?: { seq: number; type: string; at: string; actor: string; payload: Record<string, unknown> }[];
};

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/admin/api${path}`, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail?.message ?? data.message ?? '操作失败，请刷新后重试');
  return data;
}
export type L3Metrics = { episodes: number; terminal: number; managed: number; managed_rate: number | null; rated: number; rating_coverage: number | null; nss: number | null; intent_labeled: number; intent_accuracy: number | null; unauthorized_executions: number | null };
export const l3Api = {
  metrics: (from: string) => request<L3Metrics>(`/metrics/l3?since=${encodeURIComponent(from)}`),
  queue: (status = 'awaiting_approval', priority = '') => request<{ items: ServiceCase[] }>(`/cases/queue?status=${encodeURIComponent(status)}&priority=${encodeURIComponent(priority)}`),
  detail: (id: string) => request<ServiceCase>(`/cases/${encodeURIComponent(id)}`),
  decide: (id: string, body: unknown) => request<{ run_id: string }>(`/cases/${encodeURIComponent(id)}/decision`, body),
  resume: (id: string, decisionId: string) => request(`/cases/${encodeURIComponent(id)}/decisions/${encodeURIComponent(decisionId)}/resume`, {}),
  close: (id: string, revision: number) => request(`/cases/${encodeURIComponent(id)}/close`, { expected_revision: revision }),
  reopen: (id: string, revision: number) => request(`/cases/${encodeURIComponent(id)}/reopen`, { expected_revision: revision }),
};
