/** 案件详情：左 客户对话（聊天端同款只读）| 中 服务记录 + 方案与判定 | 右 人工决定与案件处理。 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CASE_LABELS } from '../../state/progress';
import { ProposalCard } from '../../components/ProposalCard';
import type { ProposalOption } from '../../types/events';
import { SessionRecord, SessionView } from '../components/SessionView';
import { l3Api } from '../l3';
import { CONDITION_TEXT, COST_TEXT, FAULT_CLASS_TEXT, GATE_TEXT, REMEDY_TEXT, needsHumanText, showValue, sla, when } from '../format';
import { useAsync } from '../useAsync';

/** 后端目前只放开换货的自动办理（D-SR-4 计划增加 parts / paid_repair）；其余处置在前端显示为不可批准而不是隐藏。 */
const APPROVABLE = new Set(['replace']);
const DECISION_TEXT: Record<string, string> = { approve: '批准', reject: '拒绝', request_info: '要求补充信息' };

export function CaseDetail() {
  const { id = '' } = useParams();
  const result = useAsync(() => l3Api.detail(id), [id]);
  const [decision, setDecision] = useState('approve');
  const [optionId, setOptionId] = useState('');
  const [note, setNote] = useState('');
  const [override, setOverride] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editCost, setEditCost] = useState<'company' | 'customer' | 'shared' | ''>('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [hover, setHover] = useState<string[]>([]);
  const row = result.data;
  const options: ProposalOption[] = row?.proposal?.options ?? [];
  const selectedOption = options.find((o) => o.option_id === optionId) ?? options[0];
  const changed = !!selectedOption && ((!!editTitle.trim() && editTitle.trim() !== selectedOption.title) || (!!editCost && editCost !== selectedOption.cost_bearer));
  const needsOverride = decision === 'approve' && (changed || !!row?.policy_decision?.needs_human || !selectedOption?.auto_allowed);
  const approvalBlocked = row?.policy_decision?.fault_class === 'unknown' || row?.policy_decision?.fault_class === 'safety';
  const remedyOpen = !!selectedOption && APPROVABLE.has(selectedOption.remedy);
  const ended = !!row && ['closed', 'closed_unresolved', 'escalated_summary'].includes(row.status);

  async function changeLifecycle(command: 'close' | 'reopen') {
    if (!row) return;
    setBusy(true); setMessage('');
    try {
      await l3Api[command](id, row.revision);
      setMessage(command === 'close' ? '案件已结案，原会话可用时已同步通知用户。' : '案件已重新受理，后续办理需要重新核实并确认方案。');
      result.reload();
    } catch (error) { setMessage(error instanceof Error ? error.message : '操作失败'); result.reload(); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!row) return;
    setBusy(true); setMessage('');
    try {
      if (!note.trim() || (needsOverride && !override.trim())) throw new Error('请填写说明及必要的覆盖政策理由。');
      await l3Api.decide(id, { decision_id: crypto.randomUUID(), expected_revision: row.revision, decision, option_id: selectedOption?.option_id ?? null, note: note.trim(), override_reason: override.trim() || null, edited_option: decision === 'approve' && changed && selectedOption ? { ...selectedOption, title: editTitle.trim() || selectedOption.title, cost_bearer: editCost || selectedOption.cost_bearer, source: 'human' } : null });
      setMessage('决定已保存并投递到会话。'); result.reload();
    } catch (error) { setMessage(error instanceof Error ? error.message : '提交失败'); result.reload(); }
    finally { setBusy(false); }
  }

  if (result.error) return <p className="empty" role="alert">{result.error} <Link className="link" to="/desk">返回工作台</Link></p>;
  if (!row) return <p className="empty">正在加载案件…</p>;
  const wait = sla(row.updated_at);
  const conditions = (row.policy_decision?.remedies ?? []).flatMap((remedy) => (remedy.conditions ?? []).map((c) => ({ remedy: remedy.remedy, ...c })));

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <h2 style={{ fontSize: 15 }}>案件 {id.slice(0, 8)} · {CASE_LABELS[row.status] ?? row.status}</h2>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12.5, marginTop: 6 }}>
              {row.complaint_risk && <span className="tag tag-critical">投诉风险</span>}
              {row.priority === 'high' && <span className="tag tag-warning">优先处理</span>}
              <span className="muted">等待 <span className="sla" data-level={wait.level}>{wait.label}</span></span>
              <span className="muted">受理 {when(row.opened_at)}</span>
              {row.external_refs.order_no && <span className="muted">订单 <span className="mono">{row.external_refs.order_no}</span></span>}
              {row.external_refs.service_order_no && <span className="muted">服务单 <span className="mono">{row.external_refs.service_order_no}</span></span>}
              {row.policy_decision && <span className="muted">故障类别 {FAULT_CLASS_TEXT[row.policy_decision.fault_class] ?? row.policy_decision.fault_class}</span>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Link className="btn" to={`/sessions/${row.session_id}`} style={{ textDecoration: 'none' }}>会话旅程</Link>
            <Link className="btn" to="/desk" style={{ textDecoration: 'none' }}>返回工作台</Link>
          </div>
        </div>
      </div>

      <div className="desk-grid">
        <section className="card">
          <h2>客户对话</h2>
          <p className="sub">与客户端一致的只读视图；步骤卡悬停可在中栏高亮依据。</p>
          <SessionView snapshot={row.snapshot} onHover={setHover} />
        </section>

        <section className="card">
          <h2>服务记录</h2>
          <SessionRecord snapshot={row.snapshot} highlight={hover} />
          <h2 style={{ marginTop: 20 }}>方案与判定依据</h2>
          {row.proposal ? (
            <ProposalCard item={{ kind: 'proposal_card', card_id: row.case_id, version: row.revision, options: options, chosen_option_id: row.proposal.chosen_option_id, policy_version: row.policy_decision?.policy_version ?? '待核实', decision_summary: `政策 ${row.policy_decision?.policy_id ?? '待核实'} · 版本 ${row.policy_decision?.policy_version ?? '—'}` }} active={false} onConfirm={() => {}} onDecline={() => {}} />
          ) : <p className="muted" style={{ fontSize: 12.5 }}>尚未生成方案。</p>}
          {conditions.length > 0 && (
            <div className="scroll-x" style={{ marginTop: 10 }}>
              <table className="data">
                <thead><tr><th>处置</th><th>条件</th><th>期望</th><th>实际</th><th>满足</th></tr></thead>
                <tbody>
                  {conditions.map((c, i) => (
                    <tr key={i}><td>{REMEDY_TEXT[c.remedy] ?? c.remedy}</td><td>{CONDITION_TEXT[c.name] ?? c.name}</td><td className="mono">{showValue(c.expected)}</td><td className="mono">{showValue(c.actual)}</td><td>{c.met ? '✓ 是' : '× 否'}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <h3 className="sub" style={{ marginTop: 14, fontWeight: 600 }}>授权检查</h3>
          {row.gate_result ? row.gate_result.checks.map((check) => (
            <p key={check.name} style={{ margin: '2px 0', fontSize: 12.5 }}>{check.passed ? '✓' : '×'} {GATE_TEXT[check.name] ?? check.name}<span className="muted"> · {check.detail}</span></p>
          )) : <p className="muted" style={{ fontSize: 12.5 }}>尚未进入授权门。</p>}
          {(row.policy_decision?.needs_human_reasons ?? []).map((reason) => <p key={reason} className="muted" style={{ fontSize: 12.5 }}>需人工：{needsHumanText(reason)}</p>)}
          {approvalBlocked && <p className="notice">故障未核实或存在安全限制，不能批准办理。可「要求补充信息」，完成核实后再批准。</p>}
        </section>

        <section className="card">
          <h2>人工决定</h2>
          <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <fieldset disabled={busy || row.status !== 'awaiting_approval'}>
              <label>处理方式
                <select value={decision} onChange={(e) => setDecision(e.target.value)}>
                  {Object.entries(DECISION_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              {options.length > 0 && (
                <label>方案
                  <select value={selectedOption?.option_id ?? ''} onChange={(e) => { setOptionId(e.target.value); setEditTitle(''); setEditCost(''); }}>
                    {options.map((o) => <option key={o.option_id} value={o.option_id}>{o.title}{APPROVABLE.has(o.remedy) ? '' : '（后端暂未放开自动办理）'}</option>)}
                  </select>
                </label>
              )}
              {decision === 'approve' && selectedOption && (
                <>
                  <label>修改方案标题（可选）<input value={editTitle} placeholder={selectedOption.title} onChange={(e) => setEditTitle(e.target.value)} /></label>
                  <label>费用承担
                    <select value={editCost || selectedOption.cost_bearer || ''} onChange={(e) => setEditCost(e.target.value as typeof editCost)}>
                      <option value="" disabled>待核实</option>
                      {Object.entries(COST_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </label>
                  {changed && <p className="notice">修改后的方案会发给用户重新确认，确认前不会执行。</p>}
                </>
              )}
              <label>说明或补充问题<textarea required value={note} onChange={(e) => setNote(e.target.value)} /></label>
              <label>覆盖政策理由{needsOverride && <span className="muted">（必填）</span>}<input value={override} required={needsOverride} onChange={(e) => setOverride(e.target.value)} /></label>
              <button className="btn" data-variant="primary" disabled={decision === 'approve' && (!remedyOpen || approvalBlocked)}>
                {decision === 'approve' ? `批准：${selectedOption ? REMEDY_TEXT[selectedOption.remedy] ?? selectedOption.title : '—'}` : DECISION_TEXT[decision]} 并恢复会话
              </button>
              {decision === 'approve' && selectedOption && !remedyOpen && <p className="muted" style={{ fontSize: 12 }}>该处置后端尚未放开自动办理。</p>}
            </fieldset>
          </form>
          {row.status !== 'awaiting_approval' && <p className="muted" style={{ fontSize: 12.5 }}>案件当前不在等待审核，决定表单不可用。</p>}
          {message && <p role="status" className="notice">{message}</p>}

          {(row.decisions?.length ?? 0) > 0 && (
            <>
              <h3 className="sub" style={{ marginTop: 14, fontWeight: 600 }}>已保存的决定</h3>
              {row.decisions!.map((d) => (
                <div key={d.decision_id} style={{ fontSize: 12.5, marginBottom: 8 }}>
                  <p style={{ margin: 0 }}><b>{DECISION_TEXT[d.decision] ?? d.decision}</b> · {d.note}</p>
                  {d.override_reason && <p className="muted" style={{ margin: 0 }}>覆盖理由：{d.override_reason}</p>}
                  {!d.consumed_input_id && (
                    <button className="btn" style={{ marginTop: 4 }} disabled={busy} onClick={() => { setBusy(true); void l3Api.resume(id, d.decision_id).then(result.reload).catch((e) => setMessage(String(e))).finally(() => setBusy(false)); }}>
                      会话未收到该决定，重新投递
                    </button>
                  )}
                </div>
              ))}
            </>
          )}

          <h3 className="sub" style={{ marginTop: 14, fontWeight: 600 }}>案件处理</h3>
          {ended ? (
            <button className="btn" disabled={busy || result.loading} onClick={() => void changeLifecycle('reopen')}>重新受理案件</button>
          ) : (
            <>
              <p className="muted" style={{ fontSize: 12.5 }}>确认人工处理已结束后结案；用户会收到通知，尚未提交的办理卡片将失效。</p>
              <button className="btn" disabled={busy || result.loading || row.status === 'executing'} onClick={() => void changeLifecycle('close')}>人工结案</button>
              {row.status === 'executing' && <p className="muted" style={{ fontSize: 12.5 }}>正在执行办理，待回执返回后可结案。</p>}
            </>
          )}
          <button className="btn" style={{ marginLeft: 8 }} onClick={result.reload}>刷新</button>
        </section>
      </div>
    </>
  );
}
