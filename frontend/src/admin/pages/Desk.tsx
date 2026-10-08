/** 坐席工作台：按状态分组的案件队列，每行带客户上下文（产品 / 问题 / 情绪）与等待时长分级。
 *  后端 queue() 尚未 join 会话事实（P2），先用会话列表接口按 session_id 拼上。 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CASE_LABELS } from '../../state/progress';
import { api } from '../api';
import { l3Api, type ServiceCase } from '../l3';
import { CASE_GROUPS, EMOTION_TEXT, SERVICE_TYPE_TEXT, WARRANTY_TEXT, defaultWindow, sla } from '../format';
import { useAsync } from '../useAsync';
import type { SessionRow } from '../types';

/** 队列行摘要：服务单类型 + 质保判断（物流类服务单没有质保判断）。 */
export function policySummary(row: ServiceCase): string {
  const types = (row.proposal?.options ?? []).map((o) => SERVICE_TYPE_TEXT[o.type] ?? o.title);
  const warranty = row.warranty ? WARRANTY_TEXT[row.warranty.status] ?? row.warranty.status : null;
  return [types.join(' / '), warranty].filter(Boolean).join(' · ') || '信息待核实';
}

export function Desk() {
  const [group, setGroup] = useState('awaiting');
  const [priority, setPriority] = useState('');
  const queue = useAsync(() => l3Api.queue('', priority), [priority]);
  const from = useMemo(() => defaultWindow(365).from, []);
  const facts = useAsync(() => api.sessions({ from, limit: 100 }), [from]);
  const bySession = useMemo(() => new Map((facts.data?.items ?? []).map((s) => [s.session_id, s])), [facts.data]);

  const items = queue.data?.items ?? [];
  const counts = Object.fromEntries(CASE_GROUPS.map((g) => [g.key, items.filter((c) => g.statuses.includes(c.status)).length]));
  const current = CASE_GROUPS.find((g) => g.key === group) ?? CASE_GROUPS[0]!;
  const rows = group === 'all' ? items : items.filter((c) => current.statuses.includes(c.status));

  return (
    <>
      <div className="filters">
        {CASE_GROUPS.map((g) => (
          <button key={g.key} className="chip" aria-pressed={group === g.key} onClick={() => setGroup(g.key)}>{g.label} <b>{counts[g.key]}</b></button>
        ))}
        <button className="chip" aria-pressed={group === 'all'} onClick={() => setGroup('all')}>全部 <b>{items.length}</b></button>
        <select value={priority} aria-label="优先级" onChange={(e) => setPriority(e.target.value)}>
          <option value="">全部优先级</option><option value="high">优先处理</option><option value="normal">普通</option>
        </select>
        <button className="btn" onClick={queue.reload}>刷新</button>
        <span className="muted" style={{ fontSize: 12 }}>{queue.loading ? '加载中…' : `${rows.length} 个案件`}</span>
      </div>

      <div className="card scroll-x">
        {queue.error && <p className="empty" role="alert">读取失败：{queue.error}</p>}
        {!queue.error && !queue.loading && rows.length === 0 && <p className="empty">当前没有符合条件的案件。</p>}
        {rows.length > 0 && (
          <table className="data">
            <thead>
              <tr><th>客户与问题</th><th>产品</th><th>情绪</th><th>状态</th><th>等待</th><th>政策结论</th><th>订单</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => <Row key={row.case_id} row={row} fact={bySession.get(row.session_id)} />)}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function Row({ row, fact }: { row: ServiceCase; fact: SessionRow | undefined }) {
  const wait = sla(row.updated_at);
  const emotion = fact?.emotion_level ?? null;
  return (
    <tr>
      <td style={{ maxWidth: 360 }}>
        <Link className="link" to={`/desk/${row.case_id}`}>{fact?.first_question || <span className="muted">（无会话摘要）</span>}</Link>
        <div className="mono muted">{row.case_id.slice(0, 8)}{row.complaint_risk && <span className="tag tag-critical">投诉风险</span>}{row.priority === 'high' && !row.complaint_risk && <span className="tag tag-warning">优先</span>}</div>
      </td>
      <td>{fact?.sku ?? <span className="muted">{fact?.category ?? '未识别'}</span>}</td>
      <td>{emotion ? <span className="badge"><i className={emotion === 'calm' ? 'role-neutral' : emotion === 'anxious' ? 'role-warning' : 'role-critical'} aria-hidden="true" />{EMOTION_TEXT[emotion] ?? emotion}</span> : <span className="muted">—</span>}</td>
      <td>{CASE_LABELS[row.status] ?? row.status}</td>
      <td><span className="sla" data-level={wait.level}>{wait.label}</span></td>
      <td className="muted" style={{ maxWidth: 260 }}>{policySummary(row)}</td>
      <td className="mono">{row.external_refs.order_no ?? <span className="muted">待核实</span>}</td>
    </tr>
  );
}
