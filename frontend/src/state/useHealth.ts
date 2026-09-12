import { useCallback, useEffect, useState } from 'react';
import { fetchHealth } from '../api/health';
import type { HealthState } from '../types/health';

const POLL_INTERVAL_MS = 10_000;
const REQUEST_TIMEOUT_MS = 5_000;

export function useHealth() {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<HealthState>({
    snapshot: null, error: null, checkedAt: null, refreshing: true,
  });
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let disposed = false;
    let pending: AbortController | null = null;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      if (pending) return;
      const controller = new AbortController();
      pending = controller;
      timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      setState((current) => ({ ...current, refreshing: true }));
      try {
        const snapshot = await fetchHealth(controller.signal);
        if (!disposed) {
          setState({ snapshot, error: null, checkedAt: new Date(), refreshing: false });
        }
      } catch {
        if (!disposed) {
          // 请求失败后清除旧快照，避免把上次的绿灯误认为当前可用。
          setState({
            snapshot: null,
            error: '暂时无法获取服务状态，将自动重试。',
            checkedAt: new Date(),
            refreshing: false,
          });
        }
      } finally {
        clearTimeout(timeout);
        pending = null;
      }
    }

    void poll();
    const interval = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      disposed = true;
      clearInterval(interval);
      clearTimeout(timeout);
      pending?.abort();
    };
  }, [revision]);

  return { ...state, refresh };
}
