/** 会话列表：筛选 + 搜索 + 翻页。点一行进旅程页。 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Badge } from '../components/Charts';
import { OUTCOME, count, defaultWindow, ms, reasonText, when } from '../format';
import { useAsync } from '../useAsync';
import type { SessionRow } from '../types';

const OUTCOMES = Object.entries(OUTCOME).map(([key, meta]) => ({ key, label: meta.label }));

export function Sessions() {
  const [q, setQ] = useState('');
  const [outcome, setOutcome] = useState('');
  const [days, setDays] = useState(7);
  const [pages, setPages] = useState<string[]>([]); // 已翻过的游标栈
  // 同 Dashboard：from 必须对 days 记忆，否则每次渲染都换值 → 无限重取
  const from = useMemo(() => defaultWindow(days).from, [days]);
  const cursor = pages[pages.length - 1];

  const list = useAsync(
    () => api.sessions({ from, q: q || undefined, outcome: outcome || undefined, cursor, limit: 30 }),
    [from, q, outcome, cursor],
  );

  function change(next: () => void) {
    setPages([]); // 改筛选条件回到第一页
    next();
  }

  return (
    <>
      <div className="filters">
        <input value={q} placeholder="搜索用户首次提问…" aria-label="搜索用户首次提问"
          onChange={(e) => change(() => setQ(e.target.value))} />
        <select value={outcome} aria-label="按结局筛选" onChange={(e) => change(() => setOutcome(e.target.value))}>
          <option value="">全部结局</option>
          {OUTCOMES.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
        <select value={days} aria-label="时间范围" onChange={(e) => change(() => setDays(Number(e.target.value)))}>
          <option value={1}>今天</option><option value={7}>近 7 天</option>
          <option value={30}>近 30 天</option><option value={365}>全部</option>
        </select>
        <span className="muted" style={{ fontSize: 12 }}>
          {list.loading ? '加载中…' : `本页 ${list.data?.items.length ?? 0} 条`}
        </span>
      </div>

      <div className="card scroll-x">
        {list.error && <p className="empty">读取失败：{list.error}</p>}
        {!list.error && (list.data?.items.length ?? 0) === 0 && !list.loading && (
          <p className="empty">这个条件下没有会话。</p>
        )}
        {(list.data?.items.length ?? 0) > 0 && (
          <table className="data">
            <thead>
              <tr>
                <th>用户问了什么</th><th>结局</th><th>原因</th><th>产品</th>
                <th className="num">轮次</th><th className="num">步骤</th><th className="num">耗时</th><th>最后活动</th>
              </tr>
            </thead>
            <tbody>
              {list.data!.items.map((row) => <Row key={row.session_id} row={row} />)}
            </tbody>
          </table>
        )}
      </div>

      <div className="filters" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <button className="btn" disabled={pages.length === 0}
          onClick={() => setPages((p) => p.slice(0, -1))}>上一页</button>
        <button className="btn" disabled={!list.data?.next_cursor}
          onClick={() => setPages((p) => [...p, list.data!.next_cursor!])}>下一页</button>
      </div>
    </>
  );
}

function Row({ row }: { row: SessionRow }) {
  return (
    <tr>
      <td style={{ maxWidth: 340 }}>
        <Link className="link" to={`/sessions/${row.session_id}`}>
          {row.first_question || <span className="muted">（无文本）</span>}
        </Link>
        <div className="mono muted">{row.session_id.slice(0, 12)}
          {row.case_verdict && ` · 已标注：${row.case_verdict}`}
          {!row.raw_available && ' · 原文已过期'}
        </div>
      </td>
      <td><Badge outcome={row.outcome} /></td>
      <td className="muted">{reasonText(row.outcome_reason)}</td>
      <td>{row.sku ?? <span className="muted">{row.category ?? '未识别'}</span>}</td>
      <td className="num">{row.runs}</td>
      <td className="num">{row.steps_executed || '—'}</td>
      <td className="num">{ms(row.total_latency_ms)}</td>
      <td className="muted">{when(row.last_run_at)}</td>
    </tr>
  );
}

export { count };
