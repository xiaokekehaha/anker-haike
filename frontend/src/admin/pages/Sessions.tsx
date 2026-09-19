/** 会话列表：筛选（结局 / 原因 / 品类 / 计划 / 关键词 / 时间窗）+ 翻页；行内带 L3 案件状态。点一行进旅程页。 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CASE_LABELS } from '../../state/progress';
import { PRODUCT_CATEGORIES } from '../../components/ChatPane';
import { api } from '../api';
import { l3Api } from '../l3';
import { Badge } from '../components/Charts';
import { EMOTION_TEXT, OUTCOME, REASON_TEXT, count, defaultWindow, ms, reasonText, when } from '../format';
import { useAsync } from '../useAsync';
import type { SessionRow } from '../types';

const OUTCOMES = Object.entries(OUTCOME).map(([key, meta]) => ({ key, label: meta.label }));
const REASONS = ['R1', 'R1b', 'R1c', 'R2', 'R3', 'R4', 'R5', 'R7', 'R8', 'solved', 'plan_done'];

export function Sessions() {
  const [q, setQ] = useState('');
  const [outcome, setOutcome] = useState('');
  const [reason, setReason] = useState('');
  const [category, setCategory] = useState('');
  const [plan, setPlan] = useState('');
  const [days, setDays] = useState(7);
  const [pages, setPages] = useState<string[]>([]); // 已翻过的游标栈
  // 同看板：from 必须对 days 记忆，否则每次渲染都换值 → 无限重取
  const from = useMemo(() => defaultWindow(days).from, [days]);
  const cursor = pages[pages.length - 1];

  const list = useAsync(
    () => api.sessions({ from, q: q || undefined, outcome: outcome || undefined, reason: reason || undefined, category: category || undefined, plan: plan || undefined, cursor, limit: 30 }),
    [from, q, outcome, reason, category, plan, cursor],
  );
  const cases = useAsync(() => l3Api.queue(''), []);
  const caseOf = useMemo(() => new Map((cases.data?.items ?? []).map((c) => [c.session_id, c])), [cases.data]);

  function change(next: () => void) { setPages([]); next(); }

  return (
    <>
      <div className="filters">
        <input value={q} placeholder="搜索用户首次提问…" aria-label="搜索用户首次提问" onChange={(e) => change(() => setQ(e.target.value))} />
        <select value={outcome} aria-label="按结局筛选" onChange={(e) => change(() => setOutcome(e.target.value))}>
          <option value="">全部结局</option>
          {OUTCOMES.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
        <select value={reason} aria-label="按原因筛选" onChange={(e) => change(() => setReason(e.target.value))}>
          <option value="">全部原因</option>
          {REASONS.map((r) => <option key={r} value={r}>{r} · {REASON_TEXT[r]}</option>)}
        </select>
        <select value={category} aria-label="按品类筛选" onChange={(e) => change(() => setCategory(e.target.value))}>
          <option value="">全部品类</option>
          {PRODUCT_CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <input value={plan} placeholder="排障计划 id" aria-label="按排障计划筛选" style={{ minWidth: 140 }} onChange={(e) => change(() => setPlan(e.target.value))} />
        <select value={days} aria-label="时间范围" onChange={(e) => change(() => setDays(Number(e.target.value)))}>
          <option value={1}>今天</option><option value={7}>近 7 天</option><option value={30}>近 30 天</option><option value={365}>近一年</option>
        </select>
        <span className="muted" style={{ fontSize: 12 }}>{list.loading ? '加载中…' : `本页 ${list.data?.items.length ?? 0} 条`}</span>
      </div>

      <div className="card scroll-x">
        {list.error && <p className="empty">读取失败：{list.error}</p>}
        {!list.error && (list.data?.items.length ?? 0) === 0 && !list.loading && <p className="empty">这个条件下没有会话。</p>}
        {(list.data?.items.length ?? 0) > 0 && (
          <table className="data">
            <thead>
              <tr>
                <th>用户问了什么</th><th>结局</th><th>原因</th><th>产品</th><th>情绪</th><th>案件</th>
                <th className="num">轮次</th><th className="num">步骤</th><th className="num">耗时</th><th>最后活动</th>
              </tr>
            </thead>
            <tbody>
              {list.data!.items.map((row) => <Row key={row.session_id} row={row} caseStatus={caseOf.get(row.session_id)?.status} caseId={caseOf.get(row.session_id)?.case_id} />)}
            </tbody>
          </table>
        )}
      </div>

      <div className="filters" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <button className="btn" disabled={pages.length === 0} onClick={() => setPages((p) => p.slice(0, -1))}>上一页</button>
        <button className="btn" disabled={!list.data?.next_cursor} onClick={() => setPages((p) => [...p, list.data!.next_cursor!])}>下一页</button>
      </div>
    </>
  );
}

function Row({ row, caseStatus, caseId }: { row: SessionRow; caseStatus?: string; caseId?: string }) {
  return (
    <tr>
      <td style={{ maxWidth: 340 }}>
        <Link className="link" to={`/sessions/${row.session_id}`}>{row.first_question || <span className="muted">（无文本）</span>}</Link>
        <div className="mono muted">{row.session_id.slice(0, 12)}{row.case_verdict && ` · 已复盘：${row.case_verdict}`}{!row.raw_available && ' · 原文已过期'}</div>
      </td>
      <td><Badge outcome={row.outcome} /></td>
      <td className="muted">{reasonText(row.outcome_reason)}</td>
      <td>{row.sku ?? <span className="muted">{row.category ?? '未识别'}</span>}</td>
      <td className="muted">{row.emotion_level ? EMOTION_TEXT[row.emotion_level] ?? row.emotion_level : '—'}</td>
      <td>{caseId ? <Link className="link" to={`/desk/${caseId}`}>{CASE_LABELS[caseStatus ?? ''] ?? caseStatus}</Link> : <span className="muted">—</span>}</td>
      <td className="num">{row.runs}</td>
      <td className="num">{row.steps_executed || '—'}</td>
      <td className="num">{ms(row.total_latency_ms)}</td>
      <td className="muted">{when(row.last_run_at)}</td>
    </tr>
  );
}

export { count };
