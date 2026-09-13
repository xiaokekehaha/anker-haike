/** 极简数据获取：一个 effect + 竞态保护。四个页面的读取模式一致，不值得引 react-query。 */
import { useCallback, useEffect, useRef, useState } from 'react';

export type Async<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    setLoading(true);
    load()
      .then((result) => { if (mine === seq.current) { setData(result); setError(null); } })
      .catch((err: unknown) => {
        if (mine !== seq.current) return;
        setError(err instanceof Error ? err.message : '加载失败');
        setData(null);
      })
      .finally(() => { if (mine === seq.current) setLoading(false); });
    // load 每次渲染都是新函数，依赖以调用方给的 deps 为准
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
