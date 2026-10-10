/** 案件页中栏：AI 交接摘要与办理记录（执行、承诺、事件）。数据来自 GET /admin/api/cases/{id}。 */
import { FACT_LABELS, stepText } from '../../components/SummaryCard';
import { CASE_LABELS } from '../../state/progress';
import type { EscalationSummary } from '../../types/snapshot';
import { when } from '../format';
import type { CaseEvent, CaseExecution } from '../l3';

const EXECUTION_TEXT: Record<string, string> = { running: '执行中', succeeded: '成功', failed: '失败', stale: '已被接管' };
const SOURCE_TEXT: Record<string, string> = { clause: '政策条款', receipt: '办理回执', action_config: '动作配置', human_decision: '人工决定' };
const EVENT_TEXT: Record<string, string> = {
  status_changed: '状态变化', updated: '案件更新', commitment: '记录承诺', execution_attached: '关联服务单',
  order_identified: '关联订单', product_identified: '确认产品', request_changed: '客户变更诉求',
  resolution_disputed: '客户反馈未解决', manual_action: '人工操作', handoff_summary: '更新交接摘要',
  review_requested: '进入审核时的客户诉求',
};
const REQUEST_TEXT: Record<string, string> = { replace: '换货', refund: '退款', address_update: '修改地址' };

function eventDetail(event: CaseEvent): string {
  const p = event.payload;
  if (event.type === 'status_changed') return `${CASE_LABELS[String(p.from)] ?? p.from} → ${CASE_LABELS[String(p.to)] ?? p.to}：${p.reason}`;
  if (event.type === 'commitment') return String(p.text);
  if (event.type === 'review_requested') return REQUEST_TEXT[String(p.requested)] ?? String(p.requested);
  if (event.type === 'request_changed') return `${REQUEST_TEXT[String(p.requested)] ?? p.requested}「${p.quote}」`;
  if (event.type === 'resolution_disputed') return `「${p.quote}」`;
  if (event.type === 'updated') return String(p.reason ?? '');
  if (event.type === 'handoff_summary') return '';
  return Object.values(p).filter((v) => typeof v === 'string').join(' · ');
}

export function HandoffSummary({ summary }: { summary: EscalationSummary | null | undefined }) {
  if (!summary) return <p className="muted" style={{ fontSize: 12.5 }}>案件尚未交接人工，没有交接摘要。</p>;
  const facts = Object.entries(summary.receipt.verified_facts ?? {});
  const steps = (summary.steps ?? []).map(stepText);
  return (
    <div className="handoff" aria-label="交接摘要">
      <p className="notice" data-kind="handoff-reason">转人工原因：{summary.reason.text}</p>
      <dl>
        <div><dt>产品</dt><dd>{summary.product}</dd></div>
        <div><dt>客户诉求</dt><dd>{summary.problem}</dd></div>
        <div><dt>已做排查</dt><dd>{steps.length ? steps.join('；') : '无'}</dd></div>
        <div><dt>观察</dt><dd>{summary.observations?.length ? summary.observations.join('；') : '无'}</dd></div>
        {summary.draft_reply && <div><dt>建议回复</dt><dd>{summary.draft_reply}</dd></div>}
      </dl>
      {facts.length > 0 && (
        <div className="scroll-x" style={{ marginTop: 10 }}>
          <table className="data" aria-label="核对字段">
            <thead><tr><th>核对字段</th><th>已核实的值</th></tr></thead>
            <tbody>{facts.map(([key, value]) => <tr key={key}><td>{FACT_LABELS[key] ?? key}</td><td className="mono">{value}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function CaseRecords({ executions = [], commitments = [], events = [] }: { executions?: CaseExecution[]; commitments?: Record<string, unknown>[]; events?: CaseEvent[] }) {
  return (
    <>
      <h3 className="sub" style={{ marginTop: 14, fontWeight: 600 }}>执行记录</h3>
      {executions.length ? (
        <div className="scroll-x">
          <table className="data" aria-label="执行记录">
            <thead><tr><th>时间</th><th>动作</th><th>结果</th><th>回执</th></tr></thead>
            <tbody>
              {executions.map((e) => (
                <tr key={e.execution_id}>
                  <td>{when(e.started_at)}</td>
                  <td className="mono">{e.action_kind}</td>
                  <td>{EXECUTION_TEXT[e.status] ?? e.status}{e.error?.needs_review ? ' · 待人工核实' : e.error?.outcome_unknown ? ' · 结果不明' : ''}</td>
                  <td>{e.receipt?.service_order_no ? <span className="mono">{String(e.receipt.service_order_no)}</span> : e.error?.message ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted" style={{ fontSize: 12.5 }}>尚未执行办理动作。</p>}
      <h3 className="sub" style={{ marginTop: 14, fontWeight: 600 }}>已对客户的承诺</h3>
      {commitments.length ? (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5 }}>
          {commitments.map((c, i) => <li key={i}>{String(c.text)}<span className="muted"> · 依据：{SOURCE_TEXT[String(c.source)] ?? String(c.source)}</span></li>)}
        </ul>
      ) : <p className="muted" style={{ fontSize: 12.5 }}>尚无承诺记录。</p>}
      <details style={{ marginTop: 14 }}>
        <summary className="sub" style={{ fontWeight: 600, cursor: 'pointer' }}>案件事件（{events.length}）</summary>
        <ol style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 12.5 }}>
          {events.map((e) => {
            const detail = eventDetail(e);
            return <li key={e.seq}><span className="muted">{when(e.at)}</span> {EVENT_TEXT[e.type] ?? e.type}{detail ? `：${detail}` : ''}</li>;
          })}
        </ol>
      </details>
    </>
  );
}
