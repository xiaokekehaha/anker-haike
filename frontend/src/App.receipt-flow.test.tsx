import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { serverEventSchema } from './api/events-schema';
import type { EscalationSummary, ReceiptCardItem, SessionSnapshot } from './types/snapshot';

vi.mock('./state/useHealth', () => ({ useHealth: () => ({ snapshot: null, error: null, refreshing: false, checkedAt: null, refresh: vi.fn() }) }));
const receiptFields = { order_no: 'OCR-001', channel: '示例渠道', purchase_date: null, amount: null };
const receiptCard: ReceiptCardItem = { kind: 'receipt_card', card_id: 'receipt', version: 6, fields: receiptFields,
  confidence: { order_no: 0.5, channel: 0.95 }, unreadable: ['purchase_date', 'amount'], confirmed_fields: null, skipped_reason: null };
const summary: EscalationSummary = { product: 'eufy X9 Pro', problem: '吸力下降', observations: [], hypotheses: [], steps: [],
  reason: { rule_id: 'R1', text: '排障后仍未解决' }, emotion: { level: 'calm', strategy: 'normal' },
  receipt: { status: 'channel_in_directory', verified_facts: { channel: '示例渠道' }, conflicts: [], next_step: '经销商在名录内，人工确认购买凭证后办理' }, model_trace: [] };
function snapshot(patch: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return { session_id: 's', stage: 'escalate', substage: 'collect_receipt', version: 4,
    timeline: [{ kind: 'user_message', id: 'u', text: '还是不吸', image_ids: [], images: [], at: '2026-09-12T00:00:00Z' }],
    pending_input: { kind: 'upload_receipt', card_id: 'upload', interrupt_id: 'upload', version: 4 },
    active_run: null, cancelled_run: null, last_error: null, ...patch };
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sse = (events: object[]) => new Response(events.map(e => `data: ${JSON.stringify(serverEventSchema.parse(e))}\n\n`).join(''));
const finalEvents = (status = 'channel_in_directory') => [
  { type: 'run_started', seq: 5, run_id: 'lookup', resumed: true, deadline_ms: 30000 },
  { type: 'escalation_summary', seq: 6, run_id: 'lookup', card_id: 'summary', summary: { ...summary, receipt: { ...summary.receipt, status } } },
  { type: 'done', seq: 7, run_id: 'lookup', reason: 'completed', version: 9 },
];

beforeEach(() => { sessionStorage.setItem('haike.session_id', 's'); });
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });

describe('A3 receipt workflow through App and HTTP/SSE', () => {
  it('uploads an image without text, edits OCR fields, confirms and displays the lookup summary', async () => {
    let latest = snapshot();
    const posted: Record<string, unknown>[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/sessions/s' && !init?.method) return json(latest);
      if (url.endsWith('/messages')) {
        const body = init?.body as FormData;
        expect(body.get('purpose')).toBe('receipt');
        expect(body.get('text')).toBe('购买凭证');
        expect(body.getAll('images')).toHaveLength(1);
        latest = snapshot({ version: 6, substage: 'confirm_fields', timeline: [...(latest.timeline ?? []), receiptCard],
          pending_input: { kind: 'confirm_receipt', card_id: 'receipt', interrupt_id: 'receipt', version: 6 } });
        return sse([
          { type: 'run_started', seq: 1, run_id: 'upload', resumed: false, deadline_ms: 30000 },
          { type: 'receipt_card', seq: 2, run_id: 'upload', card_id: 'receipt', version: 6, fields: receiptFields, confidence: receiptCard.confidence, unreadable: receiptCard.unreadable },
          { type: 'awaiting_input', seq: 3, run_id: 'upload', kind: 'confirm_receipt', card_id: 'receipt', interrupt_id: 'receipt', version: 6 },
          { type: 'done', seq: 4, run_id: 'upload', reason: 'awaiting_input', version: 6 },
        ]);
      }
      if (url.endsWith('/actions')) {
        const body = JSON.parse(String(init?.body));
        posted.push(body);
        latest = snapshot({ version: 9, pending_input: null, substage: null, timeline: [
          { ...receiptCard, confirmed_fields: body.payload.fields },
          { kind: 'escalation_summary', card_id: 'summary', summary },
        ] });
        return sse(finalEvents());
      }
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByRole('form', { name: '上传购买凭证' });
    expect(screen.getByRole('button', { name: '上传凭证' })).toBeDisabled();
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [new File(['receipt'], 'receipt.png', { type: 'image/png' })] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await screen.findByLabelText('订单号');
    await waitFor(() => expect(screen.getByLabelText('订单号')).toBeEnabled());
    expect(screen.getByText('置信度低')).toBeVisible();
    expect(screen.getByLabelText('描述你的问题')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('订单号'), { target: { value: 'CONFIRMED-009' } });
    fireEvent.click(screen.getByRole('button', { name: /^确认$/ }));
    await screen.findByText('经销商在名录内', { exact: false });
    await waitFor(() => expect(document.querySelector('[data-ui]')).toHaveAttribute('data-ui', 'idle'));
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ kind: 'confirm_receipt', expected_version: 6, card_id: 'receipt', interrupt_id: 'receipt',
      payload: { fields: { ...receiptFields, order_no: 'CONFIRMED-009' }, edited: ['order_no'] } });
    expect(screen.getByLabelText('订单号')).toHaveValue('CONFIRMED-009');
    expect(screen.getByLabelText('订单号')).toBeDisabled();
    expect(screen.getByLabelText('描述你的问题')).toBeEnabled();
    expect(screen.getByText('凭证核实事实')).toBeVisible();
  });

  it('skips collection with a reason and reaches the uncollected summary', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot())).mockResolvedValueOnce(sse(finalEvents('not_collected')))
      .mockResolvedValueOnce(json(snapshot({ version: 9, pending_input: null, timeline: [{ kind: 'escalation_summary', card_id: 'summary',
        summary: { ...summary, receipt: { ...summary.receipt, status: 'not_collected' } } }] })));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: '没有凭证，跳过' }));
    await waitFor(() => expect(document.querySelector('[data-ui]')).toHaveAttribute('data-ui', 'idle'));
    expect(JSON.parse(fetch.mock.calls[1]?.[1].body)).toMatchObject({ kind: 'skip_receipt', expected_version: 4, card_id: 'upload', interrupt_id: 'upload', payload: { reason: 'none' } });
    expect(screen.queryByRole('form', { name: '上传购买凭证' })).not.toBeInTheDocument();
    expect(screen.getByText('未收集', { exact: false })).toBeVisible();
  });

  it('keeps receipt mode, note and attachment after an upload is rejected, and permits retry', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot()))
      .mockResolvedValue(json({ code: 'images_unavailable', message: '图片存储未就绪' }, 503));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    const note = await screen.findByLabelText('凭证备注（选填）');
    fireEvent.change(note, { target: { value: '纸质发票' } });
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [new File(['receipt'], 'receipt.png', { type: 'image/png' })] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await screen.findByRole('alert');
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    expect(screen.getByLabelText('凭证备注（选填）')).toHaveValue('纸质发票');
    expect(screen.getByLabelText('待发送图片')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect((fetch.mock.calls[2]?.[1].body as FormData).get('purpose')).toBe('receipt');
  });
});
