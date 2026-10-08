import { describe, expect, it } from 'vitest';
import { reducer } from './reducer';
import { initialState } from './types';
import { parseServerEvent } from '../api/events';
import type { TimelineItem } from '../types/snapshot';

const cards = [
  { kind: 'proposal_card', options: [{ option_id: 'replace', type: 'replace', title: '提交换货单', detail: '', source: 'sop' }], decision_summary: '保内', chosen_option_id: 'replace' },
  { kind: 'retake_card', reasons: ['模糊'], guidance: ['对焦'], skipped: true },
  { kind: 'rating_card', score: 5 },
  { kind: 'execution_card', execution_id: 'ex1', action_kind: 'service_order.create', status: 'succeeded', receipt: { status: 'submitted' }, idempotency_key: 'case:service_order.create:replace' },
  { kind: 'case_changed', case_id: 'case1', status: 'tracking', reason: 'created', updated_at: '2026-09-14T00:00:00Z' },
] as const;

describe('L3 cards', () => {
  it.each(cards)('upserts $kind while keeping user results', (card) => {
    const item = { ...card, card_id: 'c1', version: 1 } as TimelineItem;
    const { kind, ...body } = card;
    const payload: Record<string, unknown> = { ...body };
    for (const key of ['confirmed_fields', 'chosen_option_id', 'skipped', 'score']) delete payload[key];
    const event = parseServerEvent({ type: kind, ...payload, card_id: 'c1', version: 2, seq: 2, run_id: 'r1', event_id: 'e2', recorded_at: '2026-09-14T00:00:00Z' });
    if (!event) throw new Error('invalid fixture');
    const next = reducer({ ...initialState, timeline: [item] }, { type: 'server_event', event });
    expect(next.timeline).toHaveLength(1);
    expect(next.timeline[0]).toMatchObject({ ...item, version: 2 });
  });
});
