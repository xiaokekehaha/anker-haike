import { beforeEach, describe, expect, it, vi } from 'vitest';
import { listRecent, recentIds, touchRecent } from './recentSessions';
import { verifyRecent } from './verifyRecent';

function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }

beforeEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

describe('verifyRecent', () => {
  it('hides only the sessions the backend says are gone', async () => {
    touchRecent('a');
    touchRecent('b');
    touchRecent('c');
    const fetch = vi.fn().mockImplementation(() => json({ alive: ['a', 'c'] }));
    vi.stubGlobal('fetch', fetch);

    expect(await verifyRecent()).toEqual({ checked: 3, missing: 1 });
    expect(listRecent().map(s => s.id)).toEqual(['c', 'a']);
    const body = JSON.parse(fetch.mock.calls[0]![1].body);
    expect(body.session_ids.sort()).toEqual(['a', 'b', 'c']);
  });

  it('restores a previously hidden session once the backend reports it again', async () => {
    touchRecent('a');
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => json({ alive: [] })));
    await verifyRecent();
    expect(listRecent()).toEqual([]);

    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => json({ alive: ['a'] })));
    await verifyRecent();
    expect(listRecent().map(s => s.id)).toEqual(['a']);
  });

  it.each([
    ['后端不可用', () => json({ code: 'sessions_unavailable' }, 503)],
    ['路由不存在', () => json({ detail: 'Not Found' }, 404)],
    ['代理把 SPA 回退当成了响应', () => new Response('<!doctype html>', { status: 200 })],
    ['形状不对', () => json({ ok: true })],
  ])('leaves the list untouched when the probe fails: %s', async (_label, respond) => {
    touchRecent('a');
    touchRecent('b');
    vi.stubGlobal('fetch', vi.fn().mockImplementation(respond));
    await expect(verifyRecent()).rejects.toBeTruthy();
    expect(listRecent().map(s => s.id)).toEqual(['b', 'a']);
  });

  it('leaves the list untouched when the network is down', async () => {
    touchRecent('a');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(verifyRecent()).rejects.toThrow();
    expect(listRecent().map(s => s.id)).toEqual(['a']);
  });

  it('skips the session being opened and makes no request when nothing is stored', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    expect(await verifyRecent()).toBeNull();

    touchRecent('current');
    expect(await verifyRecent(undefined, 'current')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    expect(recentIds()).toEqual(['current']);
  });

  it('does not mark anything after the caller aborts', async () => {
    touchRecent('a');
    const controller = new AbortController();
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => { controller.abort(); return json({ alive: [] }); }));
    expect(await verifyRecent(controller.signal)).toBeNull();
    expect(listRecent().map(s => s.id)).toEqual(['a']);
  });
});
