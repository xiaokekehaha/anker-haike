/**
 * 会话 reducer（票 06；05 §4）：纯函数，把每个 ServerEvent 映射为 timeline 变更与 ui 状态迁移。
 * timeline 项复用快照的 TimelineItem 形状，刷新后 restore 与实时流共用同一套渲染。
 */
import type { ServerEvent } from '../types/events';
import type { TimelineItem } from '../types/snapshot';
import { initialState } from './types';
import type { SessionAction, SessionState } from './types';

type Keyed = { kind: TimelineItem['kind']; key: string };

function keyOf(item: TimelineItem): Keyed {
  switch (item.kind) {
    case 'user_message':
      return { kind: item.kind, key: item.id };
    case 'assistant_message':
      return { kind: item.kind, key: item.message_id };
    case 'tool':
      return { kind: item.kind, key: item.tool_id };
    case 'evidence':
      return { kind: item.kind, key: item.items.map((e) => e.evidence_id).join('|') };
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
  if (previous.kind === 'product_card' && item.kind === 'product_card') next[idx] = { ...item, selected_sku: previous.selected_sku };
  if (previous.kind === 'step_card' && item.kind === 'step_card') next[idx] = { ...item, feedback: previous.feedback, note: previous.note };
  if (previous.kind === 'receipt_card' && item.kind === 'receipt_card') next[idx] = { ...item, confirmed_fields: previous.confirmed_fields, skipped_reason: previous.skipped_reason };
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
      const timeline = upsert(base.timeline, { kind: 'tool', tool_id: e.tool_id, name: e.name, status: e.status, summary: e.summary ?? null });
      const running = timeline.some((t) => t.kind === 'tool' && t.status === 'started');
      return { ...base, timeline, ui: running ? 'tool_running' : base.ui === 'tool_running' ? 'streaming' : base.ui };
    }
    case 'message_start': {
      let timeline = base.timeline;
      if (e.replaces) timeline = timeline.filter((t) => !(t.kind === 'assistant_message' && t.message_id === e.replaces));
      timeline = upsert(timeline, { kind: 'assistant_message', message_id: e.message_id, text: '', status: 'streaming', model_tier: null, replaces: e.replaces ?? null });
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
          t.kind === 'assistant_message' ? { ...t, status: e.status, model_tier: e.model_tier ?? null } : t,
        ),
      };
    case 'product_card':
      return { ...base, timeline: upsert(base.timeline, { kind: 'product_card', card_id: e.card_id, version: e.version, candidates: e.candidates, selected_sku: null }) };
    case 'step_card':
      return { ...base, timeline: upsert(base.timeline, { kind: 'step_card', card_id: e.card_id, version: e.version, step: e.step, feedback: null, note: null }) };
    case 'receipt_card':
      return {
        ...base,
        timeline: upsert(base.timeline, {
          kind: 'receipt_card', card_id: e.card_id, version: e.version, fields: e.fields, confidence: e.confidence ?? {}, unreadable: e.unreadable ?? [], confirmed_fields: null, skipped_reason: null,
        }),
      };
    case 'evidence':
      return { ...base, timeline: upsert(base.timeline, { kind: 'evidence', items: e.items }) };
    case 'awaiting_input':
      return { ...base, pendingInput: { kind: e.kind, interrupt_id: e.interrupt_id, card_id: e.card_id, version: e.version } };
    case 'escalation_summary':
      return { ...base, timeline: upsert(base.timeline, { kind: 'escalation_summary', card_id: e.card_id, summary: e.summary }) };
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
        pendingInput: state.pendingInput?.kind === 'upload_receipt' ? state.pendingInput : null,
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
        lastSeq: 0,
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
