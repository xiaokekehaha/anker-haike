import { useState } from 'react';
import type { ProposalCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

/** 服务单方案卡：主办方 SOP 下只有「提交给售后工具 → 人工处理」，卡片不承诺时效或费用。 */
export function ProposalCard({ item, active, disabled, onConfirm, onDecline }: { item: ProposalCardItem; active: boolean; disabled?: boolean; onConfirm: (optionId: string) => void; onDecline: (reason: 'want_other' | 'not_now' | 'request_human') => void }) {
  const [selected, setSelected] = useState(item.chosen_option_id ?? item.options[0]?.option_id ?? '');
  const locked = !active || disabled || !!item.chosen_option_id || !!item.declined_reason;
  return <section className={styles.card} aria-label="提交服务单">
    <header className={styles.cardHead}><strong>{item.retry ? '重试原申请' : '可提交的服务单'}</strong>{item.chosen_option_id && <span className={styles.doneTag}>已确认</span>}</header>
    <p>{item.decision_summary}</p>
    {item.options.map(option => <div key={option.option_id} className={styles.proposalOption}>
      <label><input type="radio" name={item.card_id} value={option.option_id} checked={selected === option.option_id} disabled={locked} onChange={() => setSelected(option.option_id)} /> {option.title}</label>
      {option.detail && <p>{option.detail}</p>}
      <small>提交后由人工处理，处理结果会回到本会话。</small>
    </div>)}
    <div className={styles.feedbackButtons}>
      <button disabled={locked || !selected} onClick={() => onConfirm(selected)}>{item.retry ? '重试原申请' : '确认提交'}</button>
      <button disabled={locked} onClick={() => onDecline('request_human')}>转人工</button>
      <button disabled={locked} onClick={() => onDecline('not_now')}>暂不办理</button>
    </div>
  </section>;
}
