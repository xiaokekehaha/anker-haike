import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CASE_LABELS } from '../../components/CaseStatus';
import { ProposalCard } from '../../components/ProposalCard';
import { ReadonlyTimeline } from '../components/ReadonlyTimeline';
import { l3Api } from '../l3';
import { useAsync } from '../useAsync';

export function CaseDetail() {
  const { id = '' } = useParams();
  const result = useAsync(() => l3Api.detail(id), [id]);
  const [decision, setDecision] = useState('approve');
  const [optionId, setOptionId] = useState('replace');
  const [note, setNote] = useState('');
  const [override, setOverride] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editCost, setEditCost] = useState<'company' | 'customer' | 'shared' | ''>('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const row = result.data;
  const selectedOption = row?.proposal?.options.find(o => o.option_id === optionId) ?? row?.proposal?.options[0];
  const changed = !!selectedOption && ((!!editTitle.trim() && editTitle.trim() !== selectedOption.title) || (!!editCost && editCost !== selectedOption.cost_bearer));
  const needsOverride = decision === 'approve' && (changed || !!row?.policy_decision?.needs_human || !selectedOption?.auto_allowed);
  const approvalBlocked = row?.policy_decision?.fault_class === 'unknown' || row?.policy_decision?.fault_class === 'safety';
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
  if (result.error) return <p role="alert">{result.error}</p>;
  if (!row) return <p>正在加载案件…</p>;
  return <section><Link to="/approvals">← 返回案件队列</Link><h2>案件 {id.slice(0, 8)} · {CASE_LABELS[row.status]}</h2>
    <div className="l3-case-grid"><section><h3>会话记录</h3><ReadonlyTimeline snapshot={row.snapshot ?? null} /></section>
    <section><h3>方案和判定依据</h3>{row.proposal && <ProposalCard item={{ kind: 'proposal_card', card_id: row.case_id, version: row.revision, options: row.proposal.options, chosen_option_id: row.proposal.chosen_option_id, policy_version: row.policy_decision?.policy_version ?? '待核实', decision_summary: '演示政策，待真实 SOP 替换' }} active={false} onConfirm={() => {}} onDecline={() => {}} />}
      <table><thead><tr><th>条件</th><th>期望</th><th>实际</th><th>满足</th></tr></thead><tbody>{row.policy_decision?.remedies?.flatMap((remedy, i) => remedy.conditions?.map((c, j) => <tr key={`${i}-${j}`}><td>{remedy.remedy} · {c.name}</td><td>{JSON.stringify(c.expected)}</td><td>{JSON.stringify(c.actual)}</td><td>{c.met ? '是' : '否'}</td></tr>))}</tbody></table>
      <h3>授权检查</h3>{row.gate_result?.checks.map(check => <p key={check.name}>{check.passed ? '✓' : '×'} {check.detail}</p>)}
      {row.policy_decision?.needs_human_reasons?.map(reason => <p key={reason}>{reason}</p>)}
      {approvalBlocked && <p>请先核实故障并解除安全限制。可选择“要求补充信息”，完成核实后再批准办理。</p>}
    </section><section><h3>人工决定</h3><form onSubmit={e => { e.preventDefault(); void submit(); }}>
      <fieldset disabled={busy || row.status !== 'awaiting_approval'}><label>处理方式<select value={decision} onChange={e => setDecision(e.target.value)}><option value="approve">批准换货</option><option value="reject">拒绝此方案</option><option value="request_info">要求补充信息</option></select></label>
        <label>方案<select value={selectedOption?.option_id ?? ''} onChange={e => { setOptionId(e.target.value); setEditTitle(''); setEditCost(''); }}>{row.proposal?.options.map(o => <option key={o.option_id} value={o.option_id}>{o.title}</option>)}</select></label>
        {decision === 'approve' && <><label>修改方案标题（可选）<input value={editTitle} placeholder={selectedOption?.title} onChange={e => setEditTitle(e.target.value)} /></label>
        <label>费用承担<select value={editCost || selectedOption?.cost_bearer || ''} onChange={e => setEditCost(e.target.value as typeof editCost)}><option value="" disabled>待核实</option><option value="company">公司承担</option><option value="customer">客户承担</option><option value="shared">双方分担</option></select></label>
        {changed && <p>修改后的方案将发送给用户重新确认，确认前不会执行。</p>}</>}
        <label>说明或补充问题<textarea required value={note} onChange={e => setNote(e.target.value)} /></label>
        <label>覆盖政策理由<input value={override} required={needsOverride} onChange={e => setOverride(e.target.value)} /></label>
        <button disabled={decision === 'approve' && (selectedOption?.remedy !== 'replace' || approvalBlocked)}>保存决定并恢复会话</button></fieldset></form>
      {message && <p role="status">{message}</p>}
      {row.decisions?.map(d => <div key={d.decision_id}><p>{d.decision}：{d.note}</p>{d.override_reason && <p>覆盖理由：{d.override_reason}</p>}{!d.consumed_input_id && <button disabled={busy} onClick={() => { setBusy(true); void l3Api.resume(id, d.decision_id).then(result.reload).catch(e => setMessage(String(e))).finally(() => setBusy(false)); }}>重新投递已保存的决定</button>}</div>)}
      <h3>案件处理</h3>
      {ended ? <button disabled={busy || result.loading} onClick={() => void changeLifecycle('reopen')}>重新受理案件</button> : <>
        <p>确认人工处理已结束后结案，用户会收到通知，尚未提交的办理卡片将失效。</p>
        <button disabled={busy || result.loading || row.status === 'executing'} onClick={() => void changeLifecycle('close')}>人工结案</button>
        {row.status === 'executing' && <p>正在执行办理，待回执返回后可结案。</p>}
      </>}
      <button onClick={result.reload}>刷新案件状态</button>
    </section></div>
  </section>;
}
