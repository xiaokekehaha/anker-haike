import { serverEventSchema } from './events-schema';
import type { ServerEvent } from '../types/events';

/** 接收已解码的 SSE data；非法事件返回 null，由后续 SSE 消费方跳过。 */
export function parseServerEvent(value: unknown): ServerEvent | null {
  const result = serverEventSchema.safeParse(value);
  if (!result.success) {
    // 不输出载荷、Zod 完整错误或用户提供的字段名，避免消息和凭证内容落日志。
    console.warn('[contracts] Dropped invalid server event', {
      code: 'invalid_server_event',
      issueCount: result.error.issues.length,
    });
    return null;
  }
  return result.data;
}
