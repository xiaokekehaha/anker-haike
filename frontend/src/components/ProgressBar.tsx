import type { Stage } from '../types/events';
import type { TimelineItem } from '../types/snapshot';
import { caseStatusOf, progressFor } from '../state/progress';
import styles from './ProgressBar.module.css';

type Props = { stage: Stage | null; timeline?: TimelineItem[]; activeIssueId?: string | null };

export function ProgressBar({ stage, timeline = [], activeIssueId }: Props) {
  const { steps, active } = progressFor(stage, caseStatusOf(timeline, activeIssueId));
  return (
    <ol className={styles.bar} style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }} aria-label="处理进度">
      {steps.map((step, i) => {
        const state = i === active ? 'active' : 'idle';
        return (
          <li key={step.key} className={styles.step} data-state={state} aria-current={state === 'active' ? 'step' : undefined}>
            <span className={styles.index} aria-hidden="true">{i + 1}</span>
            <span className={styles.text}><strong>{step.label}</strong><span>{step.hint}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
