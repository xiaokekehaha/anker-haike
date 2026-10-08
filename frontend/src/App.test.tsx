import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

vi.mock('./state/useHealth', () => ({
  useHealth: () => ({ snapshot: null, error: null, refreshing: false, checkedAt: null, refresh: vi.fn() }),
}));

function sse(events: object[]): Response {
  const body = events.map((e, i) => `id: ${i + 1}\nevent: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join('');
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

describe('chat shell wired to the session API (票 06 集成)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('shows the five-stage progress bar and starters in idle state', () => {
    render(<App />);
    const steps = screen.getAllByRole('listitem').filter((li) => li.closest('[aria-label="处理进度"]'));
    expect(steps).toHaveLength(5);
    for (const label of ['扫地机器人', '吸奶器']) expect(screen.getByRole('button', { name: new RegExp(label) })).toBeVisible();
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
  });

  it('sends a message: creates a session, streams events, shows the bubble and returns to idle', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/sessions' && init?.method === 'POST') return new Response(JSON.stringify({ session_id: 'sid1', version: 0 }), { status: 201 });
      if (url.endsWith('/messages')) {
        expect(init?.body).toBeInstanceOf(FormData);
        expect((init!.body as FormData).get('text')).toBe('eufy X10 Pro Omni 报错 6025');
        return sse([
          { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', resumed: false, deadline_ms: 25000 },
          { type: 'progress', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', stage: 'intake' },
          { type: 'progress', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', stage: 'diagnose' },
          { type: 'tool_call', seq: 4, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', tool_id: 't', name: 'knowledge.search', status: 'started' },
          { type: 'tool_call', seq: 5, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', tool_id: 't', name: 'knowledge.search', status: 'finished', summary: '命中 2 条来源' },
          { type: 'message_start', seq: 6, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', message_id: 'm1' },
          { type: 'message', seq: 7, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', message_id: 'm1', delta: '请先清理滚刷。' },
          { type: 'message_end', seq: 8, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', message_id: 'm1', status: 'completed', model_tier: 'primary' },
          { type: 'done', seq: 9, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', reason: 'completed', version: 4 },
        ]);
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText('描述你的问题'), { target: { value: 'eufy X10 Pro Omni 报错 6025' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(screen.getByTestId('assistant-bubble')).toHaveTextContent('请先清理滚刷。'));
    expect(screen.getAllByText('eufy X10 Pro Omni 报错 6025')).toHaveLength(2); // 用户气泡 + 服务记录面板「问题」
    expect(screen.getByText('命中 2 条来源')).toBeVisible(); // 工具行
    const diagnose = screen.getByText('定位故障').closest('li');
    expect(diagnose).toHaveAttribute('data-state', 'active');
    await waitFor(() => expect(document.querySelector('[data-ui]')).toHaveAttribute('data-ui', 'idle'));
    expect(sessionStorage.getItem('haike.session_id')).toBe('sid1');
    expect(screen.queryByText('不知道怎么说？看看示例')).not.toBeInTheDocument(); // 有历史后收起示例
  });

  it('renders a product card on awaiting_input and posts select_product with expected_version', async () => {
    const posted: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/sessions' && init?.method === 'POST') return new Response(JSON.stringify({ session_id: 'sid2', version: 0 }), { status: 201 });
      if (url.endsWith('/messages')) {
        return sse([
          { type: 'run_started', seq: 1, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', resumed: false, deadline_ms: 25000 },
          { type: 'product_card', seq: 2, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', card_id: 'c1', version: 3, candidates: [
            { sku: 'RV', name: 'eufy S1 Pro 扫地机器人', category: 'robot_vacuum', image: null, in_scope: true },
            { sku: 'BP', name: 'eufy S1 Pro 吸奶器', category: 'breast_pump', image: null, in_scope: false },
          ] },
          { type: 'awaiting_input', seq: 3, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', kind: 'select_product', input_token: 'c1', card_id: 'c1', version: 3 },
          { type: 'done', seq: 4, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', reason: 'awaiting_input', version: 3 },
        ]);
      }
      if (url === '/sessions/sid2' && !init?.method) return new Response(JSON.stringify({
        session_id: 'sid2', version: 5, stage: 'diagnose', substage: null,
        timeline: [{ kind: 'product_card', card_id: 'c1', version: 3, candidates: [
          { sku: 'RV', name: 'eufy S1 Pro 扫地机器人', category: 'robot_vacuum', image: null, in_scope: true },
        ], selected_sku: 'RV' }], pending_input: null, active_run: null, last_error: null, cancelled_run: null,
      }));
      if (url.endsWith('/actions')) {
        posted.push(JSON.parse(String(init?.body)));
        return sse([
          { type: 'run_started', seq: 5, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', resumed: true, deadline_ms: 25000 },
          { type: 'progress', seq: 6, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', stage: 'diagnose' },
          { type: 'done', seq: 7, event_id: 'fixture-event', recorded_at: '2026-09-13T00:00:00Z', run_id: 'r1', reason: 'completed', version: 5 },
        ]);
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText('描述你的问题'), { target: { value: 'S1 Pro 不吸了' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    // 用完整候选名，避免命中欢迎区的「扫地机器人」品类按钮（发送前仍显示）
    const choice = await screen.findByRole('button', { name: /eufy S1 Pro 扫地机器人/ });
    expect(screen.getByText('本期不支持')).toBeVisible();
    await waitFor(() => expect(choice).toBeEnabled());
    fireEvent.click(choice);
    await waitFor(() => expect(posted).toHaveLength(1), { timeout: 3000 });
    expect(posted[0]).toMatchObject({ kind: 'select_product', expected_version: 3, input_token: 'c1', card_id: 'c1', payload: { sku: 'RV' } });
    await waitFor(() => expect(document.querySelector('[data-ui]')).toHaveAttribute('data-ui', 'idle'));
  });
});
