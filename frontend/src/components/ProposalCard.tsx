import { useState } from 'react';
import type { ProposalCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

export function ProposalCard({ item, active, disabled, onConfirm, onDecline }: { item: ProposalCardItem; active: boolean; disabled?: boolean; onConfirm: (optionId: string) => void; onDecline: (reason: 'want_other' | 'not_now' | 'request_human') => void }) {
  const [selected, setSelected] = useState(item.chosen_option_id ?? item.options[0]?.option_id ?? '');
  const locked = !active || disabled || !!item.chosen_option_id || !!item.declined_reason;
  return <section className={styles.card} aria-label="选择售后方案">
    <header className={styles.cardHead}><strong>{item.retry ? '重试原申请' : '可选售后方案'}</strong>{item.chosen_option_id && <span className={styles.doneTag}>已确认</span>}</header>
    <p>{item.decision_summary}</p>
    {item.options.map(option => <div key={option.option_id} className={styles.proposalOption}>
      <label><input type="radio" name={item.card_id} value={option.option_id} checked={selected === option.option_id} disabled={locked} onChange={() => setSelected(option.option_id)} /> {option.title}</label>
      <p>费用承担：{({ company: '公司', customer: '客户', shared: '双方分担' } as Record<string, string>)[option.cost_bearer ?? ''] ?? '待核实'} · {option.auto_allowed ? '确认后核验并办理' : '需要人工办理'}</p>
      <p>{option.dispatch_estimate ? `预计创建服务单后 ${option.dispatch_estimate.working_days} 个工作日发出，以办理回执为准。` : '办理时长待人工核实。'}</p>
      {option.dispatch_estimate && <small>时效来源：演示动作配置（{option.dispatch_estimate.actions_version}）</small>}
      <details><summary>政策依据</summary><ul>{(option.clauses ?? []).map(clause => <li key={clause.clause_id}>{clause.clause_id}：{clause.text}<small>（{clause.source_url ? <a href={clause.source_url} target="_blank" rel="noreferrer">{clause.source_doc}</a> : clause.source_doc}，{clause.policy_version}）</small></li>)}</ul></details>
    </div>)}
    <div className={styles.feedbackButtons}>
      <button disabled={locked || !selected} onClick={() => onConfirm(selected)}>{item.retry ? '重试原申请' : '确认方案'}</button>
      {!item.retry && <button disabled={locked} onClick={() => onDecline('want_other')}>换一个方案</button>}
      <button disabled={locked} onClick={() => onDecline('request_human')}>转人工审核</button>
      <button disabled={locked} onClick={() => onDecline('not_now')}>暂不办理</button>
    </div>
  </section>;
}
