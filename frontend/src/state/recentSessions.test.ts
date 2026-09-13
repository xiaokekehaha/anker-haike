import { beforeEach, describe, expect, it } from 'vitest';
import { RECENT_KEY, listRecent, makeTitle, markAlive, markMissing, recentIds, touchRecent } from './recentSessions';

beforeEach(() => { localStorage.clear(); });

describe('recentSessions', () => {
  it('adds, reorders by recency and keeps the first title', () => {
    touchRecent('a', { title: '扫地机不吸尘' });
    touchRecent('b');
    expect(listRecent().map(s => s.id)).toEqual(['b', 'a']);
    touchRecent('a', { title: '别的标题', stage: 'guide' });
    const [first] = listRecent();
    expect(first!.id).toBe('a');
    expect(first!.title).toBe('扫地机不吸尘');
    expect(first!.stage).toBe('guide');
  });

  it('drops stale or malformed records', () => {
    const old = new Date(Date.now() - 49 * 3600 * 1000).toISOString();
    localStorage.setItem(RECENT_KEY, JSON.stringify([{ id: 'old', created_at: old, updated_at: old, title: null, stage: null }, { junk: true }, 'x']));
    expect(listRecent()).toEqual([]);
    localStorage.setItem(RECENT_KEY, '{not json');
    expect(listRecent()).toEqual([]);
  });

  it('caps the list at 20 entries', () => {
    for (let i = 0; i < 25; i++) touchRecent(`s${i}`);
    expect(listRecent()).toHaveLength(20);
    expect(listRecent()[0]!.id).toBe('s24');
  });

  it('hides sessions marked missing but keeps them recoverable', () => {
    touchRecent('a', { title: '还在' });
    touchRecent('b', { title: '没了' });
    markMissing(['b']);
    // 可见列表剔除，但存储里仍在——误判可逆是整个设计的前提。
    expect(listRecent().map(s => s.id)).toEqual(['a']);
    expect(recentIds()).toEqual(['b', 'a']);
    markAlive(['b']);
    expect(listRecent().map(s => s.id)).toEqual(['b', 'a']);
  });

  it('clears the missing mark when the session is touched again', () => {
    touchRecent('a');
    markMissing(['a']);
    expect(listRecent()).toEqual([]);
    touchRecent('a', { stage: 'guide' });
    expect(listRecent().map(s => s.id)).toEqual(['a']);
  });

  it('marks nothing on an empty id list', () => {
    touchRecent('a');
    const before = localStorage.getItem(RECENT_KEY);
    markMissing([]);
    markAlive([]);
    expect(localStorage.getItem(RECENT_KEY)).toBe(before);
  });

  it('truncates titles to 30 chars', () => {
    expect(makeTitle('   ')).toBeNull();
    expect(makeTitle('a  b')).toBe('a b');
    expect(makeTitle('一'.repeat(40))).toBe(`${'一'.repeat(30)}…`);
  });
});
