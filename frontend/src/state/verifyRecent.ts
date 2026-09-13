/** 最近会话列表的存活校验：首屏跑一次，把后端已回收的本地引用从可切换列表里隐去。
 *
 * 安全前提是「只信 200」——后端挂、路由不存在（部署错 / 版本回退）、DB 不可用时探针都不会
 * 返回合法结果，此时整轮跳过，一条也不动。真删除仍由 48 h 过期负责，见 recentSessions.ts。 */
import { probeSessions } from '../api/client';
import { markAlive, markMissing, recentIds } from './recentSessions';

export type VerifyResult = { checked: number; missing: number } | null;

/** @param skip 正在打开的会话：它的存活由 restore 自己判定，别在这里重复标记。 */
export async function verifyRecent(signal?: AbortSignal, skip?: string | null): Promise<VerifyResult> {
  const ids = recentIds().filter((id) => id !== skip);
  if (ids.length === 0) return null;
  const alive = new Set(await probeSessions(ids, signal));
  if (signal?.aborted) return null;
  const missing = ids.filter((id) => !alive.has(id));
  markAlive(ids.filter((id) => alive.has(id)));
  markMissing(missing);
  return { checked: ids.length, missing: missing.length };
}
