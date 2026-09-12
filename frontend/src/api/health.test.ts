import { describe, expect, it, vi } from 'vitest';
import { fetchHealth, parseHealth } from './health';

const degraded = {
  status: 'degraded',
  lane: 'domestic',
  components: {
    db: { status: 'down', detail: 'private connection details' },
    redis: { status: 'ok' },
    weknora: { status: 'ok' },
    models: { domestic: { status: 'unconfigured' }, overseas: { status: 'ok' } },
  },
};

describe('health API', () => {
  it('preserves independent component states in a 503 response', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(degraded), { status: 503 }));
    vi.stubGlobal('fetch', fetch);
    const signal = new AbortController().signal;
    const result = await fetchHealth(signal);
    expect(result.components.db.status).toBe('down');
    expect(result.components.weknora.status).toBe('ok');
    expect(result.components.models.domestic?.status).toBe('unconfigured');
    expect(JSON.stringify(result)).not.toContain('private connection details');
    expect(fetch).toHaveBeenCalledWith('/health', expect.objectContaining({ signal, cache: 'no-store' }));
  });

  it.each([
    null,
    { ...degraded, status: 'healthy' },
    { ...degraded, lane: 'missing' },
    { ...degraded, lane: 'toString' },
    { ...degraded, components: { ...degraded.components, db: { status: 'unknown' } } },
  ])('rejects incomplete or incompatible health data', (body) => {
    expect(() => parseHealth(body)).toThrow('无法读取服务状态');
  });

  it('rejects non-health errors even if the body looks like a snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(degraded), { status: 500 })));
    await expect(fetchHealth(new AbortController().signal)).rejects.toThrow('暂时无法连接服务');
  });

  it('rejects a proxy HTML error instead of showing healthy indicators', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<h1>Unavailable</h1>', { status: 503 })));
    await expect(fetchHealth(new AbortController().signal)).rejects.toThrow();
  });
});
