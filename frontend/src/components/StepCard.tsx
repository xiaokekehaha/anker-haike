import { useState } from 'react';
import type { StepCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

type Feedback = 'solved' | 'not_solved' | 'cannot_do';
type Props = { item: StepCardItem; active: boolean; disabled?: boolean; onFeedback: (feedback: Feedback, note?: string) => void; onHover?: (ids: string[]) => void };

const LABEL: Record<Feedback, string> = { solved: '解决了', not_solved: '还没解决', cannot_do: '做不到 / 跳过' };

/** 步骤卡（票 34 前端）：标题、操作、预期结果、caution、来源角标；旧卡折叠为一行。
 *  seen 是读图结果的隐式确认，排在操作之前单独一行 —— 用户要能一眼分清
 *  「我们看到的」和「让你做的」，看错了才好立刻纠正。 */
export function StepCard({ item, active, disabled, onFeedback, onHover }: Props) {
  const [note, setNote] = useState('');
  const answered = item.feedback ?? null;
  if (!active && answered) {
    return (
      <div className={styles.stepCollapsed} data-kind="step_card">
        <span>步骤 {item.step.step_no}：{item.step.title}</span><span className={styles.doneTag}>{LABEL[answered]}</span>
      </div>
    );
  }
  return (
    <section className={styles.card} data-kind="step_card" aria-label={`排障步骤 ${item.step.step_no}`} onMouseEnter={() => onHover?.(item.step.evidence_ids ?? [])} onMouseLeave={() => onHover?.([])}>
      <header className={styles.cardHead}>
        <strong>步骤 {item.step.step_no}：{item.step.title}</strong>
        {(item.step.evidence_ids?.length ?? 0) > 0 && <span className={styles.sourceTag} title="来源见下方抽屉">来源 {item.step.evidence_ids?.length}</span>}
      </header>
      {item.seen && <p className={styles.seen} data-kind="vision-echo">{item.seen}</p>}
      <p className={styles.instruction}>{item.step.instruction}</p>
      <p className={styles.expected}><span>预期结果</span>{item.step.expected_result}</p>
      {item.step.caution && <p className={styles.caution} role="note">⚠ {item.step.caution}</p>}
      {answered ? (
        <p className={styles.answered}>您的反馈：{LABEL[answered]}{item.note ? `（${item.note}）` : ''}</p>
      ) : (
        <div className={styles.feedback}>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="可补充说明（选填）" aria-label="补充说明" disabled={!active || disabled} />
          <div className={styles.feedbackButtons}>
            {(Object.keys(LABEL) as Feedback[]).map((k) => (
              <button key={k} type="button" data-feedback={k} disabled={!active || disabled} onClick={() => onFeedback(k, note.trim() || undefined)}>{LABEL[k]}</button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
