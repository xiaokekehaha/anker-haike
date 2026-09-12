import type { Stage } from '../types/events';
import styles from './ProgressBar.module.css';

export const PROGRESS_STEPS = [
  { key: 'understand', label: '理解需求', hint: '听懂问题与情绪' },
  { key: 'product', label: '确认产品', hint: '分清是哪台设备' },
  { key: 'diagnose', label: '定位故障', hint: '结合照片与知识库' },
  { key: 'guide', label: '分步排障', hint: '一次一步，反馈推进' },
  { key: 'resolve', label: '处理结果', hint: '解决或转人工' },
] as const;

const STAGE_INDEX: Record<Stage, number> = {
  intake: 0, disambiguate: 1, out_of_scope: 4, diagnose: 2, guide: 3, verify: 3, escalate: 4, done: 4,
};

type Props = { stage: Stage | null };

export function ProgressBar({ stage }: Props) {
  const active = stage === null ? -1 : STAGE_INDEX[stage];
  return (
    <ol className={styles.bar} aria-label="处理进度">
      {PROGRESS_STEPS.map((step, i) => {
        const state = active < 0 ? 'idle' : i < active ? 'done' : i === active ? 'active' : 'idle';
        return (
          <li key={step.key} className={styles.step} data-state={state} aria-current={state === 'active' ? 'step' : undefined}>
            <span className={styles.index} aria-hidden="true">{state === 'done' ? '✓' : i + 1}</span>
            <span className={styles.text}><strong>{step.label}</strong><span>{step.hint}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
