import type { ComponentHealth, HealthSnapshot, ReplayHealth } from '../types/health';

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

function replay(value: unknown): ReplayHealth | undefined {
  // 票 43：回放块缺失或形状不对都当作「非回放」，不影响其余健康展示
  if (!isRecord(value) || (value.status !== 'ok' && value.status !== 'down') || typeof value.case_id !== 'string') return undefined;
  return { status: value.status, caseId: value.case_id, ...(typeof value.title === 'string' ? { title: value.title } : {}) };
}

export function parseHealth(value: unknown): HealthSnapshot {
  if (!isRecord(value) || (value.status !== 'ok' && value.status !== 'degraded') ||
      typeof value.lane !== 'string' || !value.lane.trim() ||
      !isRecord(value.components) || !isRecord(value.components.models) ||
      !Object.hasOwn(value.components.models, value.lane)) {
    throw new Error('无法读取服务状态，请稍后重试。');
  }
  const replayHealth = replay(value.replay);
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
    ...(replayHealth ? { replay: replayHealth } : {}),
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
