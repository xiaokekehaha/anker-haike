import { z } from 'zod';

const modelStatus = z.object({
  alias: z.string(), model_id: z.string(), provider: z.string(),
  current_lane: z.boolean(), configured: z.boolean(),
  status: z.enum(['unconfigured', 'unchecked', 'checking', 'connected', 'failed']),
  detail: z.string().nullable(), latency_ms: z.number().nonnegative().nullable(),
  checked_at: z.iso.datetime({ offset: true }).nullable(),
  expires_at: z.iso.datetime({ offset: true }).nullable(),
});
const modelList = z.object({
  lane: z.string(), models: z.array(modelStatus),
  probe_enabled: z.boolean(), disabled_reason: z.string().nullable(),
});
export type ModelStatus = z.infer<typeof modelStatus>;
export type ModelList = z.infer<typeof modelList>;

export async function fetchModels(signal: AbortSignal): Promise<ModelList> {
  const response = await fetch('/models/status', { signal, cache: 'no-store' });
  if (!response.ok) throw new Error('暂时无法获取模型列表，请重试');
  return modelList.parse(await response.json());
}

export async function probeModel(alias: string, signal: AbortSignal): Promise<ModelStatus> {
  const response = await fetch(`/models/${encodeURIComponent(alias)}/probe`, {
    method: 'POST', signal, cache: 'no-store',
  });
  if (!response.ok) {
    const message = response.status === 429 ? '检测请求较多，请稍后重试'
      : response.status === 409 ? '当前环境不允许真实模型检测'
      : response.status === 404 ? '模型配置已变化，请重新打开列表'
      : '未能获取检测结果，请重试';
    throw new Error(message);
  }
  return modelStatus.parse(await response.json());
}
