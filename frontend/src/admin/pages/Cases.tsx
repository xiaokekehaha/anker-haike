/** 案例库：好案例（可沉淀）/ 坏案例（要归因）/ 待复盘，按原因标签看分布。 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { BarList } from '../components/Charts';
import { CASE_STATUS_TEXT, TAG_TEXT, VERDICT_TEXT, reasonText, when } from '../format';
import { useAsync } from '../useAsync';
import type { CaseRow } from '../types';

const VERDICTS = ['bad', 'review', 'good'] as const;

export function Cases() {
  const [verdict, setVerdict] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const list = useAsync(() => api.cases({ verdict: verdict || undefined, status: status || undefined }), [verdict, status]);
  const [busy, setBusy] = useState<string | null>(null);

  async function mark(row: CaseRow, next: string) {
    setBusy(row.case_id);
    try {
      await api.patchCase(row.case_id, { status: next });
      list.reload();
    } finally {
      setBusy(null);
    }
  }

  const items = list.data?.items ?? [];
  const byVerdict = (v: string) => items.filter((c) => c.verdict === v);

  return (
    <>
      <div className="filters">
        <button className="chip" aria-pressed={verdict === ''} onClick={() => setVerdict('')}>全部</button>
        {VERDICTS.map((v) => (
          <button key={v} className="chip" aria-pressed={verdict === v} onClick={() => setVerdict(v)}>
            {VERDICT_TEXT[v]}
          </button>
        ))}
        <select value={status} aria-label="按状态筛选" onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          {Object.entries(CASE_STATUS_TEXT).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <span className="muted" style={{ fontSize: 12 }}>
          {list.loading ? '加载中…' : `${items.length} 条`}
        </span>
      </div>

      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>坏案例的原因分布</h2>
          <p className="sub">按标签归类，决定下一轮先改哪里：知识、计划、规则还是模型。</p>
          <BarList rows={(list.data?.tag_stats ?? []).map((t) => ({
            value: TAG_TEXT[t.value] ?? t.value, sessions: t.n,
          }))} unit=" 例" />
        </div>
        <div className="card">
          <h2>进度</h2>
          <p className="sub">标注出来只是第一步，修完要回到这里标已修复。</p>
          <div className="grid kpis" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            {VERDICTS.map((v) => (
              <div key={v} className="kpi" style={{ padding: 0 }}>
                <div className="label">{VERDICT_TEXT[v]}</div>
                <div className="value">{byVerdict(v).length}</div>
                <div className="note">{byVerdict(v).filter((c) => c.status === 'fixed').length} 已修复</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card scroll-x">
        {items.length === 0 && !list.loading && (
          <p className="empty">还没有标注过案例。打开任意会话，点「标注这个会话」。</p>
        )}
        {items.length > 0 && (
          <table className="data">
            <thead>
              <tr><th>会话</th><th>判定</th><th>原因标签</th><th>结局</th><th>状态</th><th>标注时间</th><th /></tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.case_id}>
                  <td style={{ maxWidth: 320 }}>
                    <Link className="link" to={`/sessions/${row.session_id}`}>
                      {row.first_question || row.session_id.slice(0, 12)}
                    </Link>
                    {row.note && <div className="muted" style={{ fontSize: 11.5 }}>{row.note}</div>}
                  </td>
                  <td>{VERDICT_TEXT[row.verdict] ?? row.verdict}</td>
                  <td className="muted">{row.reason_tags.map((t) => TAG_TEXT[t] ?? t).join('、') || '—'}</td>
                  <td className="muted">{reasonText(row.outcome_reason ?? null)}</td>
                  <td>{CASE_STATUS_TEXT[row.status] ?? row.status}{row.fixed_in && <div className="muted mono">{row.fixed_in}</div>}</td>
                  <td className="muted">{when(row.labeled_at)}</td>
                  <td>
                    {/* 「已修复」只对要改的案例有意义；好案例的下一步是沉淀成回放 / 知识候选（Phase 4） */}
                    {row.verdict !== 'good' && row.status !== 'fixed' && (
                      <button className="btn" disabled={busy === row.case_id} onClick={() => mark(row, 'fixed')}>
                        标为已修复
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
