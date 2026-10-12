/** 研发诊断：聚合流程图、模型与检索健康、复盘记录库。 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { BarList } from '../components/Charts';
import { GraphView } from '../components/GraphView';
import { CASE_STATUS_TEXT, TAG_TEXT, VERDICT_TEXT, defaultWindow, ms, reasonText, when } from '../format';
import { useAsync } from '../useAsync';
import type { ReviewRow } from '../types';

const VERDICTS = ['bad', 'review', 'good'] as const;

export function Lab() {
  const from = useMemo(() => defaultWindow(7).from, []);
  const overview = useAsync(() => api.overview({ from, bucket: 'day', dim: 'category' }), [from]);
  const flow = useAsync(() => api.flow({ from }), [from]);
  const topology = useAsync(() => api.topology(), []);
  const [verdict, setVerdict] = useState('');
  const [status, setStatus] = useState('');
  const reviews = useAsync(() => api.reviews({ verdict: verdict || undefined, status: status || undefined }), [verdict, status]);
  const [busy, setBusy] = useState<string | null>(null);

  async function mark(row: ReviewRow, next: string) {
    setBusy(row.case_id);
    try { await api.patchReview(row.case_id, { status: next }); reviews.reload(); }
    finally { setBusy(null); }
  }
  const items = reviews.data?.items ?? [];
  const byVerdict = (v: string) => items.filter((c) => c.verdict === v);

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>整体流程（近 7 天）</h2>
        <p className="sub">从左到右按一轮里的平均步序排列；边越粗经过次数越多，节点颜色越深经过次数越多。往回跳的边不参与排序。点节点看名称，滚轮缩放。</p>
        {topology.data ? <GraphView topology={topology.data} traffic={flow.data} /> : <p className="empty">{topology.error ?? '加载流程图…'}</p>}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>模型与检索</h2>
        <p className="sub">按任务看调用量、降级与 P95 耗时。</p>
        <div className="scroll-x">
          <table className="data">
            <thead><tr><th>任务</th><th>模型</th><th className="num">调用</th><th className="num">降级</th><th className="num">出错</th><th className="num">P95</th></tr></thead>
            <tbody>
              {(overview.data?.models ?? []).map((m) => (
                <tr key={`${m.task}-${m.model_used}`}>
                  <td>{m.task}</td><td className="mono">{m.model_used ?? '—'}</td>
                  <td className="num">{m.calls}</td><td className="num">{m.fallbacks || '—'}</td><td className="num">{m.errors || '—'}</td><td className="num">{ms(m.p95_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(overview.data?.retrieval ?? []).length > 0 && (
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>检索：{overview.data!.retrieval.map((r) => `${r.kb} ${r.status} ${r.n}`).join(' · ')}</p>
        )}
      </div>

      <h2 className="row-title">复盘记录 <span>好案例沉淀、坏案例归因；与 L3 服务案件无关</span></h2>
      <div className="filters">
        <button className="chip" aria-pressed={verdict === ''} onClick={() => setVerdict('')}>全部</button>
        {VERDICTS.map((v) => <button key={v} className="chip" aria-pressed={verdict === v} onClick={() => setVerdict(v)}>{VERDICT_TEXT[v]}</button>)}
        <select value={status} aria-label="按状态筛选" onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          {Object.entries(CASE_STATUS_TEXT).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <span className="muted" style={{ fontSize: 12 }}>{reviews.loading ? '加载中…' : `${items.length} 条`}</span>
      </div>
      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>坏案例的原因分布</h2>
          <p className="sub">按标签归类，决定下一轮先改哪里：知识、计划、规则还是模型。</p>
          <BarList rows={(reviews.data?.tag_stats ?? []).map((t) => ({ value: TAG_TEXT[t.value] ?? t.value, sessions: t.n }))} unit=" 例" />
        </div>
        <div className="card">
          <h2>进度</h2>
          <p className="sub">标注出来只是第一步，修完要回到这里标已修复。导出 replay / kb 候选属 P2。</p>
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
        {items.length === 0 && !reviews.loading && <p className="empty">还没有复盘记录。打开任意会话旅程，点「标注这个会话」。</p>}
        {items.length > 0 && (
          <table className="data">
            <thead><tr><th>会话</th><th>判定</th><th>原因标签</th><th>结局</th><th>状态</th><th>标注时间</th><th /></tr></thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.case_id}>
                  <td style={{ maxWidth: 320 }}>
                    <Link className="link" to={`/sessions/${row.session_id}`}>{row.first_question || row.session_id.slice(0, 12)}</Link>
                    {row.note && <div className="muted" style={{ fontSize: 11.5 }}>{row.note}</div>}
                  </td>
                  <td>{VERDICT_TEXT[row.verdict] ?? row.verdict}</td>
                  <td className="muted">{row.reason_tags.map((t) => TAG_TEXT[t] ?? t).join('、') || '—'}</td>
                  <td className="muted">{reasonText(row.outcome_reason ?? null)}</td>
                  <td>{CASE_STATUS_TEXT[row.status] ?? row.status}{row.fixed_in && <div className="muted mono">{row.fixed_in}</div>}</td>
                  <td className="muted">{when(row.labeled_at)}</td>
                  <td>{row.verdict !== 'good' && row.status !== 'fixed' && <button className="btn" disabled={busy === row.case_id} onClick={() => mark(row, 'fixed')}>标为已修复</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
