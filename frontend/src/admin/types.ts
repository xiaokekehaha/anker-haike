/** 观测台接口的响应形状（后端 app/admin/router.py）。手写而非生成：管理端不进 make contracts 流程。
 *  会话快照直接用聊天端契约生成的 SessionSnapshot，不再手写子集。 */
import type { SessionSnapshot } from '../types/snapshot';

export type Outcome =
  | 'resolved' | 'escalated' | 'abandoned' | 'awaiting_user'
  | 'clarifying' | 'in_progress' | 'errored' | 'interrupted' | 'unknown'
  | 'closed_unresolved' | 'executed_closed' | 'human_executed' | 'consult_answered' | 'awaiting_human';

export type SessionRow = {
  session_id: string;
  created_at: string;
  last_run_at: string;
  runs: number;
  first_question: string | null;
  sku: string | null;
  category: string | null;
  product_state: string | null;
  emotion_level: string | null;
  steps_executed: number;
  clarifications?: number;
  knowledge_status: string | null;
  receipt_status?: string | null;
  outcome: Outcome;
  outcome_reason: string | null;
  model_calls: number;
  tokens: number;
  total_latency_ms: number;
  fault_plan_ids: string[];
  raw_available: boolean;
  case_verdict: string | null;
  case_tags: string[] | null;
};

export type NodeRun = {
  run_id: string;
  idx: number;
  node: string;
  prev_node: string | null;
  started_at: string;
  duration_ms: number | null;
  status: 'ok' | 'interrupt' | 'error';
  summary: Record<string, unknown> | null;
};

export type ModelCall = {
  run_id: string; node: string | null; task: string; model_used: string | null;
  lane: string | null; status: string; attempts: number; fallback_used: boolean;
  stream: boolean; latency_ms: number | null; tokens_in: number | null;
  tokens_out: number | null; error_type: string | null; created_at: string;
};

export type RetrievalCall = {
  run_id: string; node: string | null; round: number | null; kb: string | null;
  status: string; allowed_count: number | null; hits: number | null;
  top_score: number | null; latency_ms: number | null; query: string | null; created_at: string;
};

export type RunFacts = {
  run_id: string; session_id: string; seq_no: number; started_at: string;
  ended_at: string | null; duration_ms: number | null; entry: string | null;
  stage_from: string | null; stage_to: string | null; done_reason: string | null;
  error_code: string | null; first_visible_ms: number | null; card_ready_ms: number | null;
  card_kind: string | null; tokens_in: number; tokens_out: number;
  node_count: number;
  nodes: NodeRun[]; retrieval_calls: RetrievalCall[];
  /** 旅程接口里 model_calls 是数组（与 run_facts 的同名计数字段重名） */
  model_calls: ModelCall[] | number;
};

/** 复盘记录（analytics.cases）：对一个会话的人工判定，与 L3 服务案件无关。 */
export type ReviewRow = {
  case_id: string; session_id: string; run_id: string | null; verdict: 'good' | 'bad' | 'review';
  reason_tags: string[]; note: string | null; labeled_by: string | null; labeled_at: string;
  status: 'open' | 'exported' | 'fixed' | 'wontfix'; exported_to: unknown; fixed_in: string | null;
  first_question?: string | null; category?: string | null; sku?: string | null;
  outcome?: Outcome; outcome_reason?: string | null;
};

export type Journey = {
  session: SessionRow & Record<string, unknown>;
  runs: RunFacts[];
  case: ReviewRow | null;
  snapshot: SessionSnapshot | null;
};

export type Overview = {
  window: { from: string; to: string; bucket: string };
  totals: Record<string, number | string>;
  latency: Record<string, number | null>;
  rates: { self_service: number | null; closure: number | null; escalation: number | null };
  series: { at: string; sessions: number; resolved: number; escalated: number }[];
  breakdown: { value: string; sessions: number; resolved: number; escalated: number }[];
  models: { task: string; model_used: string | null; calls: number; errors: number; fallbacks: number; p95_ms: number | null; tokens_in: number; tokens_out: number }[];
  retrieval: { kb: string; status: string; n: number }[];
};

export type Flow = {
  edges: { source: string; target: string; n: number }[];
  nodes: { node: string; n: number; errors: number; interrupts: number; p50_ms: number | null }[];
  entries: { node: string; n: number }[];
};

export type Topology = {
  nodes: { id: string; stage: string }[];
  edges: { source: string; target: string; conditional: boolean }[];
  stage_order: string[];
};
