import { beforeEach, describe, expect, it } from 'vitest';
import { RECENT_KEY, listRecent, makeTitle, removeRecent, touchRecent } from './recentSessions';

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

  it('removes entries and drops stale or malformed records', () => {
    touchRecent('a');
    removeRecent('a');
    expect(listRecent()).toEqual([]);
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

  it('truncates titles to 30 chars', () => {
    expect(makeTitle('   ')).toBeNull();
    expect(makeTitle('a  b')).toBe('a b');
    expect(makeTitle('一'.repeat(40))).toBe(`${'一'.repeat(30)}…`);
  });
});
