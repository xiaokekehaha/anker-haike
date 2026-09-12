import type { ComponentHealth, HealthSnapshot } from '../types/health';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function component(value: unknown): ComponentHealth {
  if (isRecord(value) && (
    value.status === 'ok' || value.status === 'down' || value.status === 'unconfigured'
  )) {
    // 后端 detail 可能包含连接信息；只保留 UI 需要的状态。
    return { status: value.status };
  }
  throw new Error('无法读取服务状态，请稍后重试。');
}

export function parseHealth(value: unknown): HealthSnapshot {
  if (!isRecord(value) || (value.status !== 'ok' && value.status !== 'degraded') ||
      typeof value.lane !== 'string' || !value.lane.trim() ||
      !isRecord(value.components) || !isRecord(value.components.models) ||
      !Object.hasOwn(value.components.models, value.lane)) {
    throw new Error('无法读取服务状态，请稍后重试。');
  }
  return {
    status: value.status,
    lane: value.lane,
    components: {
      db: component(value.components.db),
      weknora: component(value.components.weknora),
      models: Object.fromEntries(
        Object.entries(value.components.models).map(([lane, health]) => [lane, component(health)]),
      ),
    },
  };
}

export async function fetchHealth(signal: AbortSignal): Promise<HealthSnapshot> {
  const response = await fetch('/health', {
    signal,
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  // db 故障时服务用 503 返回完整快照，其余组件仍应单独展示。
  if (!response.ok && response.status !== 503) {
    throw new Error('暂时无法连接服务，正在自动重试。');
  }
  return parseHealth(await response.json());
}
