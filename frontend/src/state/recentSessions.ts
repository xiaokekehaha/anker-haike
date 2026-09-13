/** 本机最近会话列表（spec_session_switch）：localStorage 只存「可切换的候选」，当前会话仍在 sessionStorage。 */
import { useSyncExternalStore } from 'react';
import type { Stage } from '../types/events';

export const RECENT_KEY = 'haike.recent_sessions';
const CHANGE_EVENT = 'haike:recent-sessions';
const MAX_ITEMS = 20;
/** 后端默认 24 h 过期；留一倍余量，最终以快照 404 为准。 */
const MAX_AGE_MS = 48 * 60 * 60 * 1000;
const TITLE_LEN = 30;

export type RecentSession = {
  id: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  stage: Stage | null;
};

function read(now = Date.now()): RecentSession[] {
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

let cache: { raw: string | null; list: RecentSession[] } | null = null;
function snapshot(): RecentSession[] {
  let raw: string | null = null;
  try { raw = localStorage.getItem(RECENT_KEY); } catch { /* storage unavailable */ }
  if (cache && cache.raw === raw) return cache.list;
  cache = { raw, list: read() };
  return cache.list;
}

function write(list: RecentSession[]) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, MAX_ITEMS))); } catch { /* storage unavailable */ }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function listRecent(): RecentSession[] {
  return read();
}

export function makeTitle(text: string): string | null {
  const t = text.trim().replace(/\s+/g, ' ');
  if (!t) return null;
  return t.length > TITLE_LEN ? `${t.slice(0, TITLE_LEN)}…` : t;
}

/** 新建或刷新一条记录；title 只在原来为空时写入，stage 有值才覆盖。 */
export function touchRecent(id: string, patch: { title?: string | null; stage?: Stage | null } = {}) {
  const now = new Date().toISOString();
  const list = read();
  const existing = list.find((x) => x.id === id);
  const next: RecentSession = existing
    ? { ...existing, updated_at: now, title: existing.title ?? patch.title ?? null, stage: patch.stage ?? existing.stage }
    : { id, created_at: now, updated_at: now, title: patch.title ?? null, stage: patch.stage ?? null };
  write([next, ...list.filter((x) => x.id !== id)]);
}

export function removeRecent(id: string) {
  write(read().filter((x) => x.id !== id));
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
