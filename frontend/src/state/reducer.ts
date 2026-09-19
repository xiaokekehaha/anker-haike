/**
 * 会话 reducer（票 06；05 §4）：纯函数，把每个 ServerEvent 映射为 timeline 变更与 ui 状态迁移。
 * timeline 项复用快照的 TimelineItem 形状，刷新后 restore 与实时流共用同一套渲染。
 */
import type { ServerEvent } from '../types/events';
import type { ImageRefItem, TimelineItem } from '../types/snapshot';
import { initialState } from './types';
import type { SessionAction, SessionState } from './types';

type Keyed = { kind: TimelineItem['kind']; key: string };

function imageRefs(value: unknown): ImageRefItem[] {
  if (!Array.isArray(value)) return [];
  return value.filter((ref): ref is ImageRefItem => ref !== null && typeof ref === 'object'
    && typeof ref.image_id === 'string' && (ref.purpose === 'fault' || ref.purpose === 'receipt')
    && typeof ref.sha256 === 'string' && typeof ref.mime === 'string' && typeof ref.size === 'number')
    .map(({ image_id, purpose, sha256, mime, size }) => ({ image_id, purpose, sha256, mime, size }));
}

function keyOf(item: TimelineItem): Keyed {
  switch (item.kind) {
    case 'user_message':
    case 'action':
      return { kind: item.kind, key: item.id };
    case 'assistant_message':
      return { kind: item.kind, key: item.message_id };
    case 'tool':
      return { kind: item.kind, key: item.tool_id };
    case 'evidence':
      return { kind: item.kind, key: `${item.first_seq ?? 0}:${item.items.map((e) => e.evidence_id).join('|')}` };
    default:
      return { kind: item.kind, key: item.card_id };
  }
}

/** 按 (kind, key) 幂等更新：存在则原位合并，否则追加。 */
function upsert(timeline: TimelineItem[], item: TimelineItem): TimelineItem[] {
  const k = keyOf(item);
  const idx = timeline.findIndex((t) => {
    const tk = keyOf(t);
    return tk.kind === k.kind && tk.key === k.key;
  });
  if (idx < 0) return [...timeline, item];
  const next = timeline.slice();
  const previous = timeline[idx]!;
  next[idx] = { ...previous, ...item } as TimelineItem;
  if (previous.kind === 'product_card' && item.kind === 'product_card') next[idx] = { ...item, selected_sku: previous.selected_sku, selected_unknown: previous.selected_unknown };
  if (previous.kind === 'step_card' && item.kind === 'step_card') next[idx] = { ...item, feedback: previous.feedback, note: previous.note };
  if (previous.kind === 'receipt_card' && item.kind === 'receipt_card') next[idx] = { ...item, confirmed_fields: previous.confirmed_fields, skipped_reason: previous.skipped_reason };
  if (previous.kind === 'observation_card' && item.kind === 'observation_card') next[idx] = { ...item, chosen_option_id: previous.chosen_option_id };
  return next;
}

function patch(timeline: TimelineItem[], kind: TimelineItem['kind'], key: string, fn: (t: TimelineItem) => TimelineItem): TimelineItem[] {
  return timeline.map((t) => {
    const tk = keyOf(t);
    return tk.kind === kind && tk.key === key ? fn(t) : t;
  });
}

function applyEvent(state: SessionState, e: ServerEvent, at: number): SessionState {
  const base: SessionState = { ...state, lastSeq: Math.max(state.lastSeq, e.seq), lastEventAt: at, stalled: false };
  switch (e.type) {
    case 'input_received': {
      const meta = { at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, issue_id: e.issue_id };
      const p = e.payload;
      const timeline = e.input_kind === 'message'
        ? upsert(base.timeline, { ...meta, kind: 'user_message', id: e.input_id, text: String(p.text ?? ''), image_ids: Array.isArray(p.image_ids) ? p.image_ids.map(String) : [], images: imageRefs(p.images) })
        : upsert(base.timeline, { ...meta, kind: 'action', id: e.input_id, action_kind: String(p.kind), label: ({ request_human: '请求人工', new_issue: '开始新问题', resume_issue: '继续之前的问题', step_feedback: '反馈排障结果', select_product: '选择产品' } as Record<string, string>)[String(p.kind)] ?? '提交信息' });
      return { ...base, timeline };
    }
    case 'issue_changed':
      return { ...base, timeline: base.timeline.map(item => (item.kind === 'user_message' || item.kind === 'action') && item.id === e.input_id ? { ...item, issue_id: e.resolved_issue_id } : item), activeIssueId: e.active_issue_id, issues: e.issues.map(i => ({ issue_id: String(i.issue_id), title: String(i.title ?? ''), status: String(i.status ?? '') })) };
    case 'pending_changed':
      return { ...base, pendingInput: base.pendingInput?.card_id === e.pending_id && e.status !== 'active' ? null : base.pendingInput };
    case 'summary_updated':
      return base; // Full immutable revision arrives in escalation_summary.
    case 'run_started':
      return {
        ...base,
        ui: 'streaming',
        error: null,
        activeRun: base.activeRun?.run_id === e.run_id ? base.activeRun : { run_id: e.run_id, deadline_ms: e.deadline_ms, deadline_at: new Date(at + e.deadline_ms).toISOString() },
      };
    case 'ping':
      return base;
    case 'progress':
      return { ...base, stage: e.stage, substage: e.substage ?? null };
    case 'tool_call': {
      const prior = base.timeline.find(t => t.kind === 'tool' && t.tool_id === e.tool_id);
      const timeline = upsert(base.timeline, { kind: 'tool', tool_id: e.tool_id, name: e.name, status: e.status, summary: e.summary ?? null, at: prior?.at ?? e.recorded_at, first_seq: prior?.first_seq ?? e.seq, last_seq: e.seq });
      const running = timeline.some((t) => t.kind === 'tool' && t.status === 'started');
      return { ...base, timeline, ui: running ? 'tool_running' : base.ui === 'tool_running' ? 'streaming' : base.ui };
    }
    case 'message_start': {
      let timeline = base.timeline;
      if (e.replaces) timeline = patch(timeline, 'assistant_message', e.replaces, t => t.kind === 'assistant_message' ? { ...t, status: 'replaced' } : t);
      timeline = upsert(timeline, { kind: 'assistant_message', message_id: e.message_id, text: '', status: 'streaming', model_tier: null, replaces: e.replaces ?? null, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, issue_id: e.issue_id, reply_to_input_id: e.reply_to_input_id });
      return { ...base, timeline, ui: base.ui === 'tool_running' ? 'tool_running' : 'streaming' };
    }
    case 'message': {
      const exists = base.timeline.some((t) => t.kind === 'assistant_message' && t.message_id === e.message_id);
      const timeline = exists
        ? patch(base.timeline, 'assistant_message', e.message_id, (t) => (t.kind === 'assistant_message' ? { ...t, text: t.text + e.delta } : t))
        : upsert(base.timeline, { kind: 'assistant_message', message_id: e.message_id, text: e.delta, status: 'streaming', model_tier: null, replaces: null });
      return { ...base, timeline };
    }
    case 'message_end':
      return {
        ...base,
        timeline: patch(base.timeline, 'assistant_message', e.message_id, (t) =>
          t.kind === 'assistant_message' ? { ...t, status: e.status, model_tier: e.model_tier ?? null, last_seq: e.seq } : t,
        ),
      };
    case 'product_card':
      return { ...base, timeline: upsert(base.timeline, { kind: 'product_card', card_id: e.card_id, version: e.version, issue_id: e.issue_id, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, candidates: e.candidates, allow_unknown: e.allow_unknown ?? false, note: e.note ?? null, selected_sku: null, selected_unknown: false }) };
    case 'step_card':
      return { ...base, timeline: upsert(base.timeline, { kind: 'step_card', card_id: e.card_id, version: e.version, issue_id: e.issue_id, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, step: e.step, feedback: null, note: null }) };
    case 'observation_card':
      return { ...base, timeline: upsert(base.timeline, { kind: 'observation_card', card_id: e.card_id, version: e.version, issue_id: e.issue_id, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, observation: e.observation, plan_id: e.plan_id, attempt: e.attempt, chosen_option_id: null }) };
    case 'receipt_card':
      return {
        ...base,
        timeline: upsert(base.timeline, {
          kind: 'receipt_card', card_id: e.card_id, version: e.version, issue_id: e.issue_id, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq, fields: e.fields, confidence: e.confidence ?? {}, unreadable: e.unreadable ?? [], confirmed_fields: null, skipped_reason: null,
        }),
      };
    case 'context_card': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'context_card', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'proposal_card': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'proposal_card', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'execution_card': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'execution_card', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'retake_card': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'retake_card', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'rating_card': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'rating_card', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'case_changed': {
      const { type: _type, seq, run_id: _run, event_id: _id, recorded_at, ...card } = e;
      return { ...base, timeline: upsert(base.timeline, { ...card, kind: 'case_changed', at: recorded_at, first_seq: seq, last_seq: seq }) };
    }
    case 'evidence':
      return { ...base, timeline: upsert(base.timeline, { kind: 'evidence', items: e.items, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq }) };
    case 'awaiting_input':
      return { ...base, pendingInput: { issue_id: e.issue_id, kind: e.kind, input_token: e.input_token, card_id: e.card_id, version: e.version } };
    case 'escalation_summary':
      return { ...base, timeline: upsert(base.timeline, { kind: 'escalation_summary', card_id: e.card_id, summary: e.summary, summary_id: e.summary_id, revision: e.revision, updated_at: e.updated_at, source_through_seq: e.source_through_seq, previous_card_id: e.previous_card_id, issue_id: e.issue_id, handoff_status: e.handoff_status, at: e.recorded_at, first_seq: e.seq, last_seq: e.seq }) };
    case 'error':
      return { ...base, error: { code: e.code, message: e.message, recoverable: e.recoverable }, errorAt: null };
    case 'done': {
      // completed：卡片已消费，pending 清空；awaiting_input / cancelled：保留 pending；error：进入 failed
      const pendingInput = e.reason === 'completed' ? null : base.pendingInput;
      const ui: SessionState['ui'] =
        e.reason === 'error' ? 'failed' : e.reason === 'awaiting_input' || (e.reason === 'cancelled' && pendingInput) ? 'awaiting_input' : 'idle';
      return { ...base, ui, version: e.version, activeRun: null, pendingActionId: null, pendingInput };
    }
    default:
      return base;
  }
}

export function reducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'server_event':
      return action.event.seq <= state.lastSeq ? state : applyEvent(state, action.event, action.at ?? Date.now());
    case 'session_created':
      return { ...initialState, id: action.id, version: action.version };
    case 'user_send':
      return {
        ...state,
        ui: 'streaming',
        error: null,
        stalled: false,
        lastEventAt: Date.now(),
        pendingInput: state.pendingInput,
        timeline: upsert(state.timeline, { kind: 'user_message', id: action.id, text: action.text, image_ids: action.imageIds ?? [], images: [], at: action.at }),
      };
    case 'action_sent':
      return { ...state, pendingActionId: action.action_id, error: null, errorAt: null, stalled: false, lastEventAt: Date.now() };
    case 'action_settled':
      return { ...state, pendingActionId: null };
    case 'restore': {
      const s = action.snapshot;
      const now = action.now ?? Date.now();
      const active = s.active_run && new Date(s.active_run.deadline_at).getTime() + 5000 > now ? s.active_run : null;
      return {
        ...state,
        id: s.session_id,
        stage: s.stage,
        substage: s.substage ?? null,
        version: s.version,
        timeline: s.timeline ?? [],
        lastSeq: s.last_event_seq ?? 0,
        activeIssueId: s.active_issue_id ?? null,
        issues: (s.issues ?? []).map(i => ({ issue_id: String(i.issue_id), title: String(i.title ?? ''), status: String(i.status ?? '') })),
        pendingInput: s.pending_input ?? null,
        activeRun: active ? { run_id: active.run_id, deadline_at: active.deadline_at, deadline_ms: Math.max(0, new Date(active.deadline_at).getTime() - now) } : null,
        ui: active ? 'streaming' : s.pending_input ? 'awaiting_input' : 'idle',
        // 快照里的 last_error 只来自最近一次运行；message / recoverable 与实时 error 事件同源。
        // 用户已手动关掉的那一条（按 at 认身份）不再复活：重连 / 409 冲突都会触发 restore，
        // 而最近一次运行仍是那次失败，否则关掉的提示会立刻又弹回来。
        error:
          s.last_error && s.last_error.at !== state.dismissedErrorAt
            ? { code: s.last_error.code, message: s.last_error.message ?? '', recoverable: s.last_error.recoverable ?? true }
            : null,
        errorAt: s.last_error?.at ?? null,
        dismissedErrorAt: state.dismissedErrorAt,
        stalled: false,
        pendingActionId: null,
        lastEventAt: now,
      };
    }
    case 'stream_error':
      return { ...state, ui: 'failed', error: { code: 'stream_error', message: action.message, recoverable: true }, errorAt: null };
    case 'stall':
      return { ...state, stalled: action.stalled };
    case 'recovering':
      return { ...state, ui: 'recovering' };
    case 'clear_error':
      // 记住这条错误的身份，避免后续 restore 把同一条重新挂上来
      return { ...state, error: null, dismissedErrorAt: state.errorAt ?? state.dismissedErrorAt };
    case 'notice':
      return { ...state, error: { code: 'notice', message: action.message, recoverable: false }, errorAt: null };
    case 'reset':
      return initialState;
    default:
      return state;
  }
}
