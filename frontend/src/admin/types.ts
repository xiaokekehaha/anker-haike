/** 观测台接口的响应形状（后端 app/admin/router.py）。手写而非生成：管理端不进 make contracts 流程。 */

export type Outcome =
  | 'resolved' | 'escalated' | 'abandoned' | 'awaiting_user'
  | 'clarifying' | 'in_progress' | 'errored' | 'interrupted' | 'unknown';

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
  knowledge_status: string | null;
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
  card_kind: string | null; model_calls: number; tokens_in: number; tokens_out: number;
  node_count: number;
  nodes: NodeRun[]; model_calls_list?: never; retrieval_calls: RetrievalCall[];
  /** 后端字段名与 run_facts.model_calls（计数）重名，旅程接口返回的是数组 */
  model_calls_detail?: ModelCall[];
};

export type CaseRow = {
  case_id: string; session_id: string; run_id: string | null; verdict: 'good' | 'bad' | 'review';
  reason_tags: string[]; note: string | null; labeled_by: string | null; labeled_at: string;
  status: 'open' | 'exported' | 'fixed' | 'wontfix'; exported_to: unknown; fixed_in: string | null;
  first_question?: string | null; category?: string | null; sku?: string | null;
  outcome?: Outcome; outcome_reason?: string | null;
};

export type Journey = {
  session: SessionRow & Record<string, unknown>;
  runs: (RunFacts & { model_calls: ModelCall[] | number })[];
  case: CaseRow | null;
  snapshot: Snapshot | null;
};

export type Snapshot = {
  session_id: string; version: number; stage: string; substage: string | null;
  timeline: TimelineItem[];
};

export type TimelineItem =
  | { kind: 'user_message'; id: string; text: string; at: string; image_ids: string[] }
  | { kind: 'assistant_message'; message_id: string; text: string; status: string; model_tier: string | null }
  | { kind: 'tool'; tool_id: string; name: string; status: string; summary: string | null }
  | { kind: 'product_card'; card_id: string; candidates: { sku: string; name: string }[]; selected_sku: string | null }
  | { kind: 'step_card'; card_id: string; step: { step_id: string; title: string; instruction: string; expected_result: string }; feedback: string | null; note: string | null }
  | { kind: 'receipt_card'; card_id: string; fields: Record<string, string | null> }
  | { kind: 'evidence'; items: { evidence_id: string; source: string; snippet: string; score: number }[] }
  | { kind: 'escalation_summary'; card_id: string; summary: { product: string; problem: string; reason: { rule_id: string; text: string } } };

export type Overview = {
  window: { from: string; to: string; bucket: string };
  totals: Record<string, number>;
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
