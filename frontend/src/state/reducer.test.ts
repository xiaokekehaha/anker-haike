import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { reducer } from './reducer';
import { initialState } from './types';
import type { SessionState } from './types';
import type { ServerEvent } from '../types/events';

const FIXTURE: ServerEvent[] = JSON.parse(readFileSync(path.resolve(process.cwd(), '../contracts/fixtures/events.valid.json'), 'utf-8'));

function run(events: ServerEvent[], start: SessionState = initialState): SessionState {
  return events.reduce((s, e) => reducer(s, { type: 'server_event', event: e, at: 1_000_000 }), start);
}

it('keeps image references and evidence occurrences at their original times', () => {
  const input = FIXTURE.find(e => e.type === 'input_received')!;
  const evidence = FIXTURE.find(e => e.type === 'evidence')!;
  const ref = { image_id: 'photo', purpose: 'fault', sha256: 'abc', mime: 'image/png', size: 42 };
  const state = run([
    { ...input, type: 'input_received', seq: 1, input_id: 'question', input_kind: 'message', payload: { text: '看这张图', image_ids: ['photo'], images: [ref] } },
    { ...evidence, seq: 2, recorded_at: '2026-09-13T01:00:00Z' },
    { ...evidence, seq: 3, recorded_at: '2026-09-13T01:10:00Z' },
  ]);
  const user = state.timeline[0];
  expect(user?.kind === 'user_message' && user.images).toEqual([ref]);
  expect(state.timeline.filter(t => t.kind === 'evidence').map(t => [t.first_seq, t.at])).toEqual([
    [2, '2026-09-13T01:00:00Z'], [3, '2026-09-13T01:10:00Z'],
  ]);
});

describe('session reducer (票 06)', () => {
  it('is pure and applies the shared fixture sequence without throwing', () => {
    const before = structuredClone(initialState);
    const s = run(FIXTURE);
    expect(initialState).toEqual(before);
    expect(s.lastSeq).toBe(25);
    expect(s.timeline.map((t) => t.kind)).toEqual(['tool', 'assistant_message', 'product_card', 'step_card', 'evidence', 'receipt_card', 'escalation_summary', 'user_message', 'proposal_card', 'execution_card', 'case_changed', 'retake_card', 'rating_card']);
  });

  it('drives idle → streaming → idle on run_started/done and tracks stage + version', () => {
    const rs = FIXTURE.find((e) => e.type === 'run_started')!;
    const s1 = reducer(initialState, { type: 'server_event', event: rs, at: 5 });
    expect(s1.ui).toBe('streaming');
    expect(s1.activeRun?.run_id).toBe(rs.run_id);
    const s2 = reducer(s1, { type: 'server_event', event: { type: 'progress', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rs.run_id, stage: 'diagnose' } as ServerEvent });
    expect(s2.stage).toBe('diagnose');
    const s3 = reducer(s2, { type: 'server_event', event: { type: 'done', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rs.run_id, reason: 'completed', version: 4 } as ServerEvent });
    expect(s3.ui).toBe('idle');
    expect(s3.version).toBe(4);
    expect(s3.activeRun).toBeNull();
  });

  it('aggregates message deltas by message_id and marks the aborted message as replaced', () => {
    const rid = 'r';
    const evs: ServerEvent[] = [
      { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, resumed: false, deadline_ms: 25000 },
      { type: 'message_start', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm1' },
      { type: 'message', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm1', delta: '先清理' },
      { type: 'message_end', seq: 4, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm1', status: 'aborted', model_tier: 'primary' },
      { type: 'message_start', seq: 5, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm2', replaces: 'm1' },
      { type: 'message', seq: 6, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm2', delta: '请先清理' },
      { type: 'message', seq: 7, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm2', delta: '滚刷。' },
      { type: 'message_end', seq: 8, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, message_id: 'm2', status: 'completed', model_tier: 'fallback' },
    ] as ServerEvent[];
    const s = run(evs);
    const bubbles = s.timeline.filter((t) => t.kind === 'assistant_message');
    // 被替换的回复保留在时间线上并标记 replaced（AssistantBubble 显示「此回复已被后续答复替换」），不再删除。
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0]).toMatchObject({ message_id: 'm1', text: '先清理', status: 'replaced' });
    expect(bubbles[1]).toMatchObject({ message_id: 'm2', text: '请先清理滚刷。', status: 'completed', model_tier: 'fallback', replaces: 'm1' });
  });

  it('enters tool_running on tool_call started and back to streaming when finished; failed keeps flow', () => {
    const rid = 'r';
    const base = run([{ type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, resumed: false, deadline_ms: 25000 }] as ServerEvent[]);
    const s1 = reducer(base, { type: 'server_event', event: { type: 'tool_call', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, tool_id: 't', name: 'knowledge.search', status: 'started' } as ServerEvent });
    expect(s1.ui).toBe('tool_running');
    const s2 = reducer(s1, { type: 'server_event', event: { type: 'tool_call', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, tool_id: 't', name: 'knowledge.search', status: 'failed', summary: '知识库暂不可用' } as ServerEvent });
    expect(s2.ui).toBe('streaming');
    expect(s2.timeline.filter((t) => t.kind === 'tool')).toHaveLength(1);
    expect(s2.timeline[0]).toMatchObject({ kind: 'tool', status: 'failed', summary: '知识库暂不可用' });
  });

  it('awaiting_input + done(awaiting_input) yields awaiting_input ui with pending card; card upsert is idempotent by card_id', () => {
    const rid = 'r';
    const card = { type: 'product_card', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, card_id: 'c1', version: 3, candidates: [{ sku: 'A', name: 'A', category: 'robot_vacuum', image: null, in_scope: true }] } as ServerEvent;
    const s = run([
      { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, resumed: false, deadline_ms: 25000 },
      card,
      card, // 重发（恢复时 await_input 重跑）
      { type: 'awaiting_input', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, kind: 'select_product', input_token: 'c1', card_id: 'c1', version: 3 },
      { type: 'done', seq: 4, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, reason: 'awaiting_input', version: 3 },
    ] as ServerEvent[]);
    expect(s.ui).toBe('awaiting_input');
    expect(s.pendingInput?.card_id).toBe('c1');
    expect(s.timeline.filter((t) => t.kind === 'product_card')).toHaveLength(1);
  });

  it('error → done(error) ends in failed with error kept; restore from snapshot rebuilds state', () => {
    const rid = 'r';
    const s = run([
      { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, resumed: false, deadline_ms: 25000 },
      { type: 'error', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, code: 'node_failed', message: 'boom', recoverable: false, retry_with_same_action: false },
      { type: 'done', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: rid, reason: 'error', version: 2 },
    ] as ServerEvent[]);
    expect(s.ui).toBe('failed');
    expect(s.error?.code).toBe('node_failed');
    const restored = reducer(s, {
      type: 'restore',
      now: 1_000,
      snapshot: { session_id: 'sid', version: 7, stage: 'guide', timeline: [{ kind: 'user_message', id: 'u1', text: 'hi', image_ids: [], images: [], at: 't' }], pending_input: { kind: 'step_feedback', input_token: 'c9', card_id: 'c9', version: 7 }, active_run: null, last_error: null, cancelled_run: null, substage: null },
    });
    expect(restored).toMatchObject({ id: 'sid', version: 7, stage: 'guide', ui: 'awaiting_input' });
    expect(restored.timeline).toHaveLength(1);
    // 快照没带 last_error：成功推进后不该再挂着上一轮的错误
    expect(restored.error).toBeNull();
    const withError = reducer(s, {
      type: 'restore',
      now: 1_000,
      snapshot: { session_id: 'sid', version: 7, stage: 'guide', timeline: [], pending_input: null, active_run: null, cancelled_run: null, substage: null,
        last_error: { code: 'node_failed', message: '规则服务不可用', recoverable: false, at: 't' } },
    });
    // 快照带错误时，文案与 recoverable 跟实时 error 事件一致，不再退回空 message
    expect(withError.error).toEqual({ code: 'node_failed', message: '规则服务不可用', recoverable: false });
    const streaming = reducer(s, { type: 'restore', now: 1_000, snapshot: { session_id: 'sid', version: 7, stage: 'diagnose', timeline: [], pending_input: null, active_run: { run_id: 'r2', started_at: 't', deadline_at: new Date(30_000).toISOString() }, last_error: null, cancelled_run: null, substage: null } });
    expect(streaming.ui).toBe('streaming');
    expect(streaming.activeRun?.run_id).toBe('r2');
  });

  it('用户关掉的快照错误不会被后续 restore 复活，新的错误仍然弹出', () => {
    const snap = (last_error: { code: string; message: string; recoverable: boolean; at: string } | null) => ({
      type: 'restore' as const,
      now: 1_000,
      snapshot: { session_id: 'sid', version: 7, stage: 'guide' as const, timeline: [], pending_input: null, active_run: null, cancelled_run: null, substage: null, last_error },
    });
    const err = { code: 'node_failed', message: '规则服务不可用', recoverable: false, at: 't1' };

    const shown = reducer(initialState, snap(err));
    expect(shown.error?.code).toBe('node_failed');

    const dismissed = reducer(shown, { type: 'clear_error' });
    expect(dismissed.error).toBeNull();

    // 重连 / 409 冲突都会再次 restore，而最近一次运行仍是那次失败
    expect(reducer(dismissed, snap(err)).error).toBeNull();

    // 换一条新错误（at 不同）必须照常弹出
    const next = reducer(dismissed, snap({ ...err, at: 't2' }));
    expect(next.error?.code).toBe('node_failed');
    // 新错误同样可以再被关掉
    expect(reducer(next, { type: 'clear_error' }).error).toBeNull();
  });
});

it('ignores replayed deltas and stale done events', () => {
  const events: ServerEvent[] = [
    { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r', resumed: false, deadline_ms: 25000 },
    { type: 'message_start', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r', message_id: 'm' },
    { type: 'message', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r', message_id: 'm', delta: '清理滚刷' },
  ];
  const state = run(events);
  expect(run([events[2]!], state)).toEqual(state);
  expect(run([{ type: 'done', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'old', reason: 'completed', version: 1 }], state)).toEqual(state);
});

it('keeps the snapshot deadline and selected result when replay starts', () => {
  const restored = reducer(initialState, { type: 'restore', now: 1000, snapshot: {
    session_id: 's', version: 8, stage: 'diagnose', substage: null,
    timeline: [{ kind: 'product_card', card_id: 'c', version: 3, candidates: [], selected_sku: 'RV' }],
    active_run: { run_id: 'r', started_at: new Date(0).toISOString(), deadline_at: new Date(25000).toISOString() },
    pending_input: null, last_error: null, cancelled_run: null,
  } });
  const state = run([
    { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r', resumed: true, deadline_ms: 25000 },
    { type: 'product_card', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r', card_id: 'c', version: 3, candidates: [{ sku: 'RV', name: '扫地机', category: 'robot_vacuum', in_scope: true }] },
  ], restored);
  expect(state.activeRun?.deadline_at).toBe(new Date(25000).toISOString());
  expect(state.timeline[0]).toMatchObject({ selected_sku: 'RV' });
});

it('keeps a repeated step card unique and preserves recorded feedback', () => {
  const fixture = FIXTURE.find((e) => e.type === 'step_card')!;
  const first = run([fixture]);
  const timeline = first.timeline.map(t => t.kind === 'step_card' ? { ...t, feedback: 'not_solved' as const, note: '仍有异响' } : t);
  const replayed = run([{ ...fixture, seq: fixture.seq + 1 }], { ...first, timeline });
  expect(replayed.timeline).toHaveLength(1);
  expect(replayed.timeline[0]).toMatchObject({ feedback: 'not_solved', note: '仍有异响' });
});
