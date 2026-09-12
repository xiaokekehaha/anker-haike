import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useHealth } from './useHealth';

const healthy = {
  status: 'ok', lane: 'domestic',
  components: { db: { status: 'ok' }, weknora: { status: 'ok' }, models: { domestic: { status: 'ok' } } },
};
const response = () => new Response(JSON.stringify(healthy));

describe('health polling lifecycle', () => {
  it('checks immediately, repeats every 10 seconds and stops on unmount', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockImplementation(async () => response());
    vi.stubGlobal('fetch', fetch);
    const { result, unmount } = renderHook(useHealth);
    await act(async () => {});
    expect(result.current.snapshot?.status).toBe('ok');
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(9_999); });
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetch).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears stale green status after failure and can recover through manual refresh', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockImplementationOnce(async () => response())
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockImplementation(async () => response());
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useHealth);
    await act(async () => {});
    expect(result.current.snapshot?.status).toBe('ok');
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.snapshot).toBeNull();
    expect(result.current.error).toBeTruthy();
    await act(async () => { result.current.refresh(); });
    expect(result.current.snapshot?.status).toBe('ok');
    expect(result.current.error).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('aborts a hung request at 5 seconds and retries at the next poll', async () => {
    vi.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    const fetch = vi.fn().mockImplementationOnce((_url: string, options: RequestInit) => {
      requestSignal = options.signal ?? undefined;
      return new Promise((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
    }).mockImplementation(async () => response());
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(useHealth);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(requestSignal?.aborted).toBe(true);
    expect(result.current.refreshing).toBe(false);
    expect(result.current.error).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(result.current.snapshot?.status).toBe('ok');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('ignores a late response from the cleaned-up StrictMode effect', async () => {
    vi.useFakeTimers();
    let resolveOld: ((response: Response) => void) | undefined;
    const signals: AbortSignal[] = [];
    const fetch = vi.fn().mockImplementationOnce((_url: string, options: RequestInit) => {
      if (options.signal) signals.push(options.signal);
      return new Promise<Response>((resolve) => { resolveOld = resolve; });
    }).mockImplementation(async () => response());
    vi.stubGlobal('fetch', fetch);
    const { result, unmount } = renderHook(useHealth, { wrapper: StrictMode });
    await act(async () => {});
    expect(signals[0]?.aborted).toBe(true);
    await act(async () => {
      resolveOld?.(new Response(JSON.stringify({ ...healthy, status: 'degraded' })));
    });
    expect(result.current.snapshot?.status).toBe('ok');
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(fetch).toHaveBeenCalledTimes(3);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
