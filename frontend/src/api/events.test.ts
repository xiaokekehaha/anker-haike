// @vitest-environment node
import { readFileSync } from 'node:fs';
import { beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { parseServerEvent } from './events';
import type { PendingKind, ServerEvent } from '../types/events';
import type { ActionConflict, ActionRequest, ActionResult } from '../types/actions';
import type { SessionSnapshot, TimelineItem } from '../types/snapshot';

const fixtures: unknown = JSON.parse(readFileSync(
  new URL('../../../contracts/fixtures/events.valid.json', import.meta.url), 'utf8',
));
if (!Array.isArray(fixtures)) throw new Error('Expected shared event fixtures to be an array');
const samples: unknown[] = fixtures;

beforeEach(() => { vi.spyOn(console, 'warn').mockImplementation(() => {}); });

describe('shared event contract', () => {
  it.each(samples)('accepts the shared sample %# through Zod', (sample) => {
    expect(parseServerEvent(sample)).not.toBeNull();
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('covers the 15 protocol variants and generates discriminated types', () => {
    const parsed = samples.map(parseServerEvent);
    expect(new Set(parsed.map((event) => event?.type)).size).toBe(24);
    const event = parsed.find((event) => event?.type === 'step_card');
    if (!event || event.type !== 'step_card') throw new Error('Missing step_card sample');
    expectTypeOf(event.step.evidence_ids).toEqualTypeOf<string[] | undefined>();
    expectTypeOf<PendingKind>().toEqualTypeOf<'select_product' | 'step_feedback' | 'upload_receipt' | 'confirm_receipt' | 'confirm_proposal' | 'upload_retake' | 'rate_satisfaction'>();
    expectTypeOf<ActionResult['replayed']>().toEqualTypeOf<boolean | undefined>();
    expectTypeOf<ActionConflict['code']>().toEqualTypeOf<'stale_version' | 'stale_card' | 'not_allowed_now' | 'run_active'>();
    expectTypeOf<ActionRequest['kind']>().toEqualTypeOf<'select_product' | 'step_feedback' | 'confirm_receipt' | 'skip_receipt' | 'request_human' | 'new_issue' | 'resume_issue' | 'confirm_proposal' | 'decline_proposal' | 'skip_retake' | 'rate_satisfaction'>();
    expectTypeOf<TimelineItem>().toEqualTypeOf<NonNullable<SessionSnapshot['timeline']>[number]>();
  });

  it.each<PendingKind>(['select_product', 'step_feedback', 'upload_receipt', 'confirm_receipt'])(
    'accepts pending input kind %s', (kind) => {
      expect(parseServerEvent({
        type: 'awaiting_input', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'fixture_run', kind,
        input_token: 'fixture_interrupt', card_id: 'fixture_card', version: 0,
      })).not.toBeNull();
    },
  );

  it.each([
    null,
    [],
    '{"type":"ping"}',
    { type: 'unknown_event', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run' },
    { type: 'ping', seq: '1', event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run' },
    { type: 'ping', seq: 0, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run' },
    { type: 'ping', seq: 1.5, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run' },
    { type: 'ping', seq: 1 },
    { type: 'ping', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', unexpected: true },
    { type: 'progress', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', stage: 'invented_stage' },
    { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', resumed: false, deadline_ms: 0 },
    { type: 'product_card', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', card_id: 'card', version: 0, candidates: [] },
    { type: 'done', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', reason: 'completed', version: -1 },
  ])('drops invalid data %# and logs a diagnostic', (value) => {
    expect(parseServerEvent(value)).toBeNull();
    expect(console.warn).toHaveBeenCalledWith('[contracts] Dropped invalid server event', {
      code: 'invalid_server_event', issueCount: expect.any(Number),
    });
  });

  it('rejects flattened step/summary objects and unknown nested fields', () => {
    for (const sample of samples) {
      const event = parseServerEvent(sample);
      if (event?.type === 'step_card') {
        const { step, ...rest } = event;
        expect(parseServerEvent({ ...rest, ...step })).toBeNull();
        expect(parseServerEvent({ ...event, step: { ...step, extra: true } })).toBeNull();
      }
      if (event?.type === 'escalation_summary') {
        const { summary, ...rest } = event;
        expect(parseServerEvent({ ...rest, ...summary })).toBeNull();
      }
      if (event?.type === 'evidence') {
        expect(parseServerEvent({ ...event, items: event.items.map((item) => ({ ...item, score: 1.1 })) })).toBeNull();
      }
    }
  });

  it('does not log message bodies, receipts, untrusted keys or complete validation errors', () => {
    const sensitive = 'PRIVATE-DEMO-ORDER-CONTENT';
    parseServerEvent({ type: 'message', seq: 0, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', delta: sensitive, [sensitive]: true });
    const warnings = vi.mocked(console.warn).mock.calls;
    expect(warnings).toHaveLength(1);
    expect(JSON.stringify(warnings)).not.toContain(sensitive);
  });

  it('keeps valid events flowing after dropping an invalid event', () => {
    const events = [
      { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', resumed: false, deadline_ms: 1_000 },
      { type: 'bad', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run' },
      { type: 'done', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'run', reason: 'completed', version: 1 },
    ].map(parseServerEvent).filter((event): event is ServerEvent => event !== null);
    expect(events.map((event) => event.type)).toEqual(['run_started', 'done']);
  });
});
