import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSession } from './useSession';
import type { SessionSnapshot } from '../types/snapshot';

const pending = { kind: 'select_product', interrupt_id: 'c', card_id: 'c', version: 4 } as const;
const candidate = { sku: 'RV', name: '扫地机', category: 'robot_vacuum', in_scope: true, image: null };
function snapshot(patch: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return { session_id: 's', version: 4, stage: 'diagnose', substage: null, timeline: [], pending_input: null, active_run: null, last_error: null, cancelled_run: null, ...patch };
}
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
function events(items: object[]) { return new Response(items.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')); }
function started(seq = 1) { return { type: 'run_started', seq, run_id: 'r', resumed: false, deadline_ms: 25000 }; }
function done(seq = 2, reason = 'completed') { return { type: 'done', seq, run_id: 'r', reason, version: 5 }; }
function active() { return { run_id: 'r', started_at: new Date().toISOString(), deadline_at: new Date(Date.now() + 25000).toISOString() }; }
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
function openStream(items: object[]) {
  const cancel = vi.fn();
  const response = new Response(new ReadableStream<Uint8Array>({
    start(c) { c.enqueue(new TextEncoder().encode(items.map(e => `data: ${JSON.stringify(e)}\n\n`).join(''))); }, cancel,
  }));
  return { response, cancel };
}

beforeEach(() => { sessionStorage.clear(); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('session recovery lifecycle', () => {
  it.each([null, pending])('restores persisted idle or pending state', async (pending_input) => {
    sessionStorage.setItem('haike.session_id', 's');
    const fetch = vi.fn().mockResolvedValue(json(snapshot({ pending_input })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.ui).toBe(pending_input ? 'awaiting_input' : 'idle'));
    await waitFor(() => expect(result.current.state.version).toBe(4));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('replays an active run from zero without duplicating snapshot text or extending deadline', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    const running = active();
    const final = snapshot({ version: 5, timeline: [{ kind: 'assistant_message', message_id: 'm', text: '清理滚刷', status: 'completed', model_tier: 'primary', replaces: null }] });
    const stream = openStream([
      started(), { type: 'message_start', seq: 2, run_id: 'r', message_id: 'm' },
      { type: 'message', seq: 3, run_id: 'r', message_id: 'm', delta: '清理' },
      { type: 'message', seq: 3, run_id: 'r', message_id: 'm', delta: '清理' },
      { type: 'message', seq: 4, run_id: 'r', message_id: 'm', delta: '滚刷' }, done(5),
    ]);
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ ...final, active_run: running })))
      .mockResolvedValueOnce(stream.response).mockResolvedValueOnce(json(final));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(result.current.state.ui).toBe('idle'));
    expect(String(fetch.mock.calls[1]?.[0])).toContain('after_seq=0');
    expect(result.current.state.timeline).toEqual(final.timeline);
    expect(stream.cancel).toHaveBeenCalledOnce(); // done 即结束，不等连接关闭
  });

  it('keeps the saved session on network failure, but removes a confirmed 404', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(json({}, 404)));
    const first = renderHook(useSession);
    await waitFor(() => expect(first.result.current.state.ui).toBe('failed'));
    expect(sessionStorage.getItem('haike.session_id')).toBe('s');
    first.unmount();
    const second = renderHook(useSession);
    await waitFor(() => expect(second.result.current.state.id).toBeNull());
    expect(sessionStorage.getItem('haike.session_id')).toBeNull();
  });

  it('ignores delayed snapshot results after reset', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    const late = deferred<Response>();
    const fetch = vi.fn().mockReturnValue(late.promise);
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    act(() => result.current.reset());
    await act(async () => late.resolve(json(snapshot({ pending_input: pending }))));
    expect(result.current.state.id).toBeNull();
    expect(result.current.state.timeline).toEqual([]);
    expect(fetch.mock.calls[0]?.[1].signal.aborted).toBe(true);
  });

  it('does not resurrect a session when creation completes after reset', async () => {
    const late = deferred<Response>();
    const fetch = vi.fn().mockReturnValue(late.promise);
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    let sending!: Promise<boolean>;
    act(() => { sending = result.current.send('你好'); });
    act(() => result.current.reset());
    await act(async () => { late.resolve(json({ session_id: 'old', version: 0 })); await sending; });
    expect(result.current.state.id).toBeNull();
    expect(sessionStorage.getItem('haike.session_id')).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('handles StrictMode cleanup and aborts the active request on unmount', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    const first = deferred<Response>();
    const fetch = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(json(snapshot({ pending_input: pending })));
    vi.stubGlobal('fetch', fetch);
    const { result, unmount } = renderHook(useSession, { wrapper: StrictMode });
    await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
    expect(fetch.mock.calls[0]?.[1].signal.aborted).toBe(true);
    await act(async () => first.resolve(json(snapshot({ version: 1 }))));
    expect(result.current.state.version).toBe(4);
    unmount();
  });

  it('recovers an early EOF and bounds repeated broken reconnections', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url === '/sessions') return json({ session_id: 's', version: 0 });
      if (url.endsWith('/messages')) return events([started()]);
      if (url === '/sessions/s') return json(snapshot({ active_run: active() }));
      return events([]);
    });
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await act(async () => result.current.send('你好'));
    expect(result.current.state.ui).toBe('failed');
    expect(fetch.mock.calls.filter(([url]) => url.includes('/events?'))).toHaveLength(3);
    expect(result.current.state.error?.message).toContain('连接多次中断');
  });

  it('shows the 15 second hint, then recovers at deadline plus grace without extending on ping', async () => {
    vi.useFakeTimers();
    const stream = openStream([started()]);
    const fetch = vi.fn().mockResolvedValueOnce(json({ session_id: 's', version: 0 }))
      .mockResolvedValueOnce(stream.response).mockResolvedValueOnce(json(snapshot({ pending_input: pending })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    let sending!: Promise<boolean>;
    await act(async () => { sending = result.current.send('你好'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(16000); });
    expect(result.current.state.stalled).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); await sending; });
    expect(result.current.state.ui).toBe('awaiting_input');
    expect(stream.cancel).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('cancels the server run, aborts the stream and restores the pending card', async () => {
    const stream = openStream([started()]);
    const fetch = vi.fn().mockResolvedValueOnce(json({ session_id: 's', version: 0 }))
      .mockResolvedValueOnce(stream.response).mockResolvedValueOnce(json({}))
      .mockResolvedValueOnce(json(snapshot({ pending_input: pending, cancelled_run: { run_id: 'r', at: new Date().toISOString() } })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    let sending!: Promise<boolean>;
    await act(async () => { sending = result.current.send('你好'); });
    await waitFor(() => expect(result.current.state.activeRun).not.toBeNull());
    await act(async () => { await result.current.cancel(); await sending; });
    expect(fetch.mock.calls[2]?.[0]).toBe('/sessions/s/cancel');
    expect(JSON.parse(fetch.mock.calls[2]?.[1].body)).toEqual({ run_id: 'r' });
    expect(stream.cancel).toHaveBeenCalledOnce();
    expect(result.current.state.ui).toBe('awaiting_input');
    expect(result.current.state.pendingInput).toEqual(pending);
  });
});

describe('action conflicts and retry', () => {
  it.each([true, false])('retries exactly once only if the server permits it (%s)', async (allowed) => {
    sessionStorage.setItem('haike.session_id', 's');
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ pending_input: pending })))
      .mockImplementation(async () => events([
        started(), { type: 'error', seq: 2, run_id: 'r', code: 'node_failed', message: '失败', recoverable: true, retry_with_same_action: allowed }, done(3, 'error'),
      ]));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
    await act(async () => result.current.act({ kind: 'select_product', payload: { sku: 'RV' } }));
    const posts = fetch.mock.calls.filter(([url]) => String(url).endsWith('/actions'));
    expect(posts).toHaveLength(allowed ? 2 : 1);
    if (allowed) expect(posts[0]?.[1].body).toBe(posts[1]?.[1].body);
    expect(result.current.state.ui).toBe('failed');
    expect(result.current.state.pendingActionId).toBeNull();
  });

  it('uses the 409 snapshot as authority without reposting the old action to the new card', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    const latest = snapshot({ version: 9, pending_input: { ...pending, card_id: 'new', interrupt_id: 'new', version: 9 },
      timeline: [{ kind: 'product_card', card_id: 'new', version: 9, candidates: [candidate], selected_sku: null }] });
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ pending_input: pending })))
      .mockResolvedValueOnce(json({ code: 'stale_card', snapshot: latest }, 409));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
    await act(async () => result.current.act({ kind: 'select_product', payload: { sku: 'RV' } }));
    expect(result.current.state.version).toBe(9);
    expect(result.current.state.timeline).toEqual(latest.timeline);
    expect(result.current.state.pendingInput?.card_id).toBe('new');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('resumes the active run supplied by a 409', async () => {
    sessionStorage.setItem('haike.session_id', 's');
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ pending_input: pending })))
      .mockResolvedValueOnce(json({ code: 'run_active', snapshot: snapshot({ active_run: active() }) }, 409))
      .mockResolvedValueOnce(events([started(), done()])).mockResolvedValueOnce(json(snapshot({ version: 8 })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
    await act(async () => result.current.act({ kind: 'select_product', payload: { sku: 'RV' } }));
    expect(fetch.mock.calls[2]?.[0]).toContain('/runs/r/events?after_seq=0');
    expect(result.current.state.version).toBe(8);
    expect(result.current.state.ui).toBe('idle');
  });
});

it('accepts a successful second attempt with the exact original action body', async () => {
  sessionStorage.setItem('haike.session_id', 's');
  const selected = snapshot({ version: 8, timeline: [{ kind: 'product_card', card_id: 'c', version: 4, candidates: [candidate], selected_sku: 'RV' }] });
  const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ pending_input: pending })))
    .mockResolvedValueOnce(events([started(), { type: 'error', seq: 2, run_id: 'r', code: 'node_failed', message: '失败', recoverable: true, retry_with_same_action: true }, done(3, 'error')]))
    .mockResolvedValueOnce(events([{ ...started(4), run_id: 'retry' }, { ...done(5), run_id: 'retry' }]))
    .mockResolvedValueOnce(json(selected));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(useSession);
  await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
  await act(async () => result.current.act({ kind: 'select_product', payload: { sku: 'RV' } }));
  expect(fetch.mock.calls[1]?.[1].body).toBe(fetch.mock.calls[2]?.[1].body);
  expect(result.current.state.error).toBeNull();
  expect(result.current.state.ui).toBe('idle');
  expect(result.current.state.timeline).toEqual(selected.timeline);
});

it('does not resume an expired run, and keeps pending input usable', async () => {
  sessionStorage.setItem('haike.session_id', 's');
  const fetch = vi.fn().mockResolvedValue(json(snapshot({ active_run: { ...active(), deadline_at: new Date(Date.now() - 6000).toISOString() }, pending_input: pending })));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(useSession);
  await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
  expect(result.current.state.activeRun).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('aborts an open stream on unmount without issuing a server cancellation', async () => {
  const stream = openStream([started()]);
  const fetch = vi.fn().mockResolvedValueOnce(json({ session_id: 's', version: 0 })).mockResolvedValueOnce(stream.response);
  vi.stubGlobal('fetch', fetch);
  const { result, unmount } = renderHook(useSession);
  let sending!: Promise<boolean>;
  await act(async () => { sending = result.current.send('你好'); });
  await waitFor(() => expect(result.current.state.activeRun).not.toBeNull());
  unmount();
  await sending;
  expect(stream.cancel).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[1]?.[1].signal.aborted).toBe(true);
});

it('surfaces cancellation errors instead of pretending the run was cancelled', async () => {
  const stream = openStream([started()]);
  const fetch = vi.fn().mockResolvedValueOnce(json({ session_id: 's', version: 0 })).mockResolvedValueOnce(stream.response)
    .mockResolvedValueOnce(json({ code: 'server_error', message: '取消失败' }, 500));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(useSession);
  let sending!: Promise<boolean>;
  await act(async () => { sending = result.current.send('你好'); });
  await waitFor(() => expect(result.current.state.activeRun).not.toBeNull());
  await act(async () => { await result.current.cancel(); await sending; });
  expect(result.current.state.ui).toBe('failed');
  expect(result.current.state.error?.message).toBe('取消失败');
  expect(result.current.state.activeRun?.run_id).toBe('r');
});

it('coalesces rapid repeated action clicks while the request is pending', async () => {
  sessionStorage.setItem('haike.session_id', 's');
  const response = deferred<Response>();
  const fetch = vi.fn().mockResolvedValueOnce(json(snapshot({ pending_input: pending })))
    .mockReturnValueOnce(response.promise).mockResolvedValueOnce(json(snapshot()));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(useSession);
  await waitFor(() => expect(result.current.state.ui).toBe('awaiting_input'));
  let first!: Promise<void>;
  await act(async () => {
    first = result.current.act({ kind: 'select_product', payload: { sku: 'RV' } });
    await result.current.act({ kind: 'select_product', payload: { sku: 'RV' } });
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  await act(async () => { response.resolve(events([started(), done()])); await first; });
  expect(result.current.state.pendingActionId).toBeNull();
});

describe('session switching (spec_session_switch)', () => {
  beforeEach(() => { localStorage.clear(); });

  it('records the created session and its first message title in the recent list', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(json({ session_id: 'n1', version: 0 }, 201))
      .mockResolvedValueOnce(events([started(), done()]))
      .mockResolvedValue(json(snapshot({ session_id: 'n1' })));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await act(async () => { await result.current.send('扫地机不吸尘了'); });
    await waitFor(() => expect(result.current.state.ui).toBe('idle'));
    expect(result.current.recent[0]).toMatchObject({ id: 'n1', title: '扫地机不吸尘了' });
    expect(sessionStorage.getItem('haike.session_id')).toBe('n1');
  });

  it('switchTo restores another session and keeps the old one in the recent list', async () => {
    sessionStorage.setItem('haike.session_id', 'a');
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/sessions/a')) return json(snapshot({ session_id: 'a', stage: 'guide', timeline: [{ kind: 'user_message', id: 'u', text: '会话 A', image_ids: [], images: [], at: new Date().toISOString() }] }));
      if (url.endsWith('/sessions/b')) return json(snapshot({ session_id: 'b', stage: 'diagnose' }));
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.stage).toBe('guide'));
    expect(result.current.recent.map(s => s.id)).toEqual(['a']);
    expect(result.current.recent[0]!.title).toBe('会话 A');

    await act(async () => { await result.current.switchTo('b'); });
    expect(result.current.state.id).toBe('b');
    expect(result.current.state.stage).toBe('diagnose');
    expect(sessionStorage.getItem('haike.session_id')).toBe('b');
    expect(result.current.recent.map(s => s.id)).toEqual(['b', 'a']);

    await act(async () => { await result.current.switchTo('b'); });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('switchTo an expired session drops it from the list and resets with a notice', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ code: 'session_not_found' }, 404));
    vi.stubGlobal('fetch', fetch);
    localStorage.setItem('haike.recent_sessions', JSON.stringify([{ id: 'gone', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), title: null, stage: null }]));
    const { result } = renderHook(useSession);
    expect(result.current.recent).toHaveLength(1);
    await act(async () => { await result.current.switchTo('gone'); });
    expect(result.current.state.id).toBeNull();
    expect(result.current.state.error?.code).toBe('notice');
    expect(result.current.recent).toEqual([]);
    expect(sessionStorage.getItem('haike.session_id')).toBeNull();
  });

  it('startNew cancels an active run before clearing the tab reference', async () => {
    sessionStorage.setItem('haike.session_id', 'a');
    const running = active();
    const stream = deferred<Response>();
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/sessions/a')) return json(snapshot({ session_id: 'a', active_run: running }));
      if (url.includes('/events')) return stream.promise;
      if (url.endsWith('/cancel') && init?.method === 'POST') return json({ cancelled: true });
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useSession);
    await waitFor(() => expect(result.current.state.activeRun?.run_id).toBe('r'));
    await act(async () => { await result.current.startNew(); });
    expect(fetch.mock.calls.some(([u, i]) => String(u).endsWith('/sessions/a/cancel') && (i as RequestInit)?.method === 'POST')).toBe(true);
    expect(result.current.state.id).toBeNull();
    expect(sessionStorage.getItem('haike.session_id')).toBeNull();
    expect(result.current.recent.map(s => s.id)).toEqual(['a']);
  });
});
