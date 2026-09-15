/** 本机最近会话列表（spec_session_switch）：localStorage 只存「可切换的候选」，当前会话仍在 sessionStorage。 */
import { useSyncExternalStore } from 'react';
import type { Stage } from '../types/events';

export const RECENT_KEY = 'haike.recent_sessions';
const CHANGE_EVENT = 'haike:recent-sessions';
const MAX_ITEMS = 20;
/** 后端默认 24 h 回收；留一倍余量兜底。日常剔除靠首屏存活探测（verifyRecent），
 *  这里只负责物理删除——包括被标记缺失但始终没等到后端恢复的那些。 */
const MAX_AGE_MS = 48 * 60 * 60 * 1000;
const TITLE_LEN = 30;

export type RecentSession = {
  id: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  stage: Stage | null;
  case_status?: string | null;
  /** 后端确认不存在的时刻。只隐藏不删除：万一是环境异常（连错库等）误判，
   *  下一轮探测确认存在就会清掉标记，会话自动回到列表；物理删除仍交给 48 h 过期。 */
  missing_since?: string | null;
};

/** 存储里所有未过期的记录，含被标记缺失的——写回时必须用它，否则 touch 一次就把标记项永久丢了。 */
function readAll(now = Date.now()): RecentSession[] {
  let raw: string | null = null;
  try { raw = localStorage.getItem(RECENT_KEY); } catch { return []; }
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x): x is RecentSession => !!x && typeof x === 'object' && typeof (x as RecentSession).id === 'string' && typeof (x as RecentSession).updated_at === 'string')
      .filter((x) => now - new Date(x.updated_at).getTime() < MAX_AGE_MS)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, MAX_ITEMS);
  } catch { return []; }
}

function visible(list: RecentSession[]): RecentSession[] {
  return list.filter((x) => !x.missing_since);
}

let cache: { raw: string | null; list: RecentSession[] } | null = null;
function snapshot(): RecentSession[] {
  let raw: string | null = null;
  try { raw = localStorage.getItem(RECENT_KEY); } catch { /* storage unavailable */ }
  if (cache && cache.raw === raw) return cache.list;
  cache = { raw, list: visible(readAll()) };
  return cache.list;
}

function write(list: RecentSession[]) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, MAX_ITEMS))); } catch { /* storage unavailable */ }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** 可切换的会话（不含已确认缺失的）。 */
export function listRecent(): RecentSession[] {
  return visible(readAll());
}

/** 参与存活探测的 id：连同已标记的一起探，这样恢复后能把标记清掉。 */
export function recentIds(): string[] {
  return readAll().map((x) => x.id);
}

/** 探测确认不存在：打标记而非删除。 */
export function markMissing(ids: readonly string[]) {
  if (ids.length === 0) return;
  const at = new Date().toISOString();
  const targets = new Set(ids);
  const list = readAll();
  if (!list.some((x) => targets.has(x.id) && !x.missing_since)) return;
  write(list.map((x) => (targets.has(x.id) && !x.missing_since ? { ...x, missing_since: at } : x)));
}

/** 探测确认存在：清除此前的缺失标记。 */
export function markAlive(ids: readonly string[]) {
  if (ids.length === 0) return;
  const targets = new Set(ids);
  const list = readAll();
  if (!list.some((x) => targets.has(x.id) && x.missing_since)) return;
  write(list.map((x) => (targets.has(x.id) && x.missing_since ? { ...x, missing_since: null } : x)));
}

export function makeTitle(text: string): string | null {
  const t = text.trim().replace(/\s+/g, ' ');
  if (!t) return null;
  return t.length > TITLE_LEN ? `${t.slice(0, TITLE_LEN)}…` : t;
}

/** 新建或刷新一条记录；title 只在原来为空时写入，stage 有值才覆盖。 */
export function touchRecent(id: string, patch: { title?: string | null; stage?: Stage | null; case_status?: string | null } = {}) {
  const now = new Date().toISOString();
  const list = readAll();
  const existing = list.find((x) => x.id === id);
  // 能 touch 说明这会话此刻是活的，顺手把可能的缺失标记清掉。
  const next: RecentSession = existing
    ? { ...existing, updated_at: now, title: existing.title ?? patch.title ?? null, stage: patch.stage ?? existing.stage, missing_since: null }
    : { id, created_at: now, updated_at: now, title: patch.title ?? null, stage: patch.stage ?? null, missing_since: null };
  if ('case_status' in patch) next.case_status = patch.case_status;
  write([next, ...list.filter((x) => x.id !== id)]);
}


function subscribe(cb: () => void) {
  window.addEventListener(CHANGE_EVENT, cb);
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(CHANGE_EVENT, cb);
    window.removeEventListener('storage', cb);
  };
}
const EMPTY: RecentSession[] = [];

export function useRecentSessions(): RecentSession[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY);
}
