import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CASE_LABELS } from '../../components/CaseStatus';
import { l3Api } from '../l3';
import { useAsync } from '../useAsync';

export function Approvals() {
  const [status, setStatus] = useState('awaiting_approval');
  const [priority, setPriority] = useState('');
  const result = useAsync(() => l3Api.queue(status, priority), [status, priority]);
  return <section><h2>售后案件与审批</h2><div className="filters">
    <label>状态 <select value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option>{Object.entries(CASE_LABELS).map(([status, label]) => <option key={status} value={status}>{label}</option>)}</select></label>
    <label>优先级 <select value={priority} onChange={e => setPriority(e.target.value)}><option value="">全部</option><option value="high">优先处理</option><option value="normal">普通</option></select></label>
    <button onClick={result.reload}>刷新</button></div>
    {result.error && <p role="alert">{result.error}</p>}{result.loading && <p>正在加载案件…</p>}
    <table><thead><tr><th>案件</th><th>订单号</th><th>状态</th><th>优先级</th><th>等待时间</th><th>政策</th></tr></thead><tbody>{result.data?.items.map(row => <tr key={row.case_id}>
      <td><Link to={`/approvals/${row.case_id}`}>{row.case_id.slice(0, 8)}</Link></td><td>{row.external_refs.order_no ?? '待核实'}</td><td>{CASE_LABELS[row.status]}</td><td>{row.complaint_risk ? '投诉风险 · 优先' : row.priority === 'high' ? '优先' : '普通'}</td>
      <td>{Math.max(0, Math.round((Date.now() - Date.parse(row.updated_at)) / 60000))} 分钟</td><td>{row.policy_decision?.policy_id ?? '信息待核实'}</td>
    </tr>)}</tbody></table>{result.data?.items.length === 0 && <p className="empty">当前没有符合条件的案件。</p>}
  </section>;
}
