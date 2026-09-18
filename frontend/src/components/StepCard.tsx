import { useState } from 'react';
import type { ObservationAnswer, StepCardItem, StepObservation } from '../types/snapshot';
import styles from './Cards.module.css';

type Feedback = 'solved' | 'not_solved' | 'cannot_do';
type Props = {
  item: StepCardItem;
  active: boolean;
  disabled?: boolean;
  onFeedback: (feedback: Feedback, note?: string, observations?: ObservationAnswer[]) => void;
  onHover?: (ids: string[]) => void;
};

const LABEL: Record<Feedback, string> = { solved: '解决了', not_solved: '还没解决', cannot_do: '做不到 / 跳过' };

/** 已记录的观察答案 → 「问题：选项」文字；unknown 选项照样显示，让用户看到自己没有被记成阴性。 */
export function observationSummary(observations: StepObservation[] | undefined, answers: ObservationAnswer[] | undefined): string[] {
  return (answers ?? []).flatMap((a) => {
    const obs = observations?.find((o) => o.observation_id === a.observation_id);
    const option = obs?.options.find((o) => o.option_id === a.option_id);
    return obs && option ? [`${obs.question}${option.label}`] : [];
  });
}

/** 步骤卡（票 34 前端）：标题、操作、预期结果、caution、来源角标；旧卡折叠为一行。
 *  seen 是读图结果的隐式确认，排在操作之前单独一行 —— 用户要能一眼分清
 *  「我们看到的」和「让你做的」，看错了才好立刻纠正。
 *  observations（design §3.1）是「检查得到什么」，与「问题是否解决」分开：每个观察一组单选，
 *  不选保持未知，绝不默认成阴性；随三态反馈一起提交。 */
export function StepCard({ item, active, disabled, onFeedback, onHover }: Props) {
  const [note, setNote] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const answered = item.feedback ?? null;
  const observations = item.step.observations ?? [];
  const recorded = observationSummary(observations, item.observation_answers);
  if (!active && answered) {
    return (
      <div className={styles.stepCollapsed} data-kind="step_card">
        <span>步骤 {item.step.step_no}：{item.step.title}</span><span className={styles.doneTag}>{LABEL[answered]}</span>
        {recorded.length > 0 && <span className={styles.observed}>{recorded.join('；')}</span>}
      </div>
    );
  }
  const submit = (feedback: Feedback) => {
    const selected: ObservationAnswer[] = Object.entries(answers).map(([observation_id, option_id]) => ({ observation_id, option_id }));
    // 没选观察时不传第三个参数：保持未知，也让旧的两参数调用方 / 测试不受影响
    if (selected.length > 0) onFeedback(feedback, note.trim() || undefined, selected);
    else onFeedback(feedback, note.trim() || undefined);
  };
  return (
    <section className={styles.card} data-kind="step_card" data-pending={active && !answered ? true : undefined} aria-label={`排障步骤 ${item.step.step_no}`} onMouseEnter={() => onHover?.(item.step.evidence_ids ?? [])} onMouseLeave={() => onHover?.([])}>
      <header className={styles.cardHead}>
        <strong>步骤 {item.step.step_no}：{item.step.title}</strong>
        {(item.step.evidence_ids?.length ?? 0) > 0 && <span className={styles.sourceTag} title="依据见右侧服务记录">依据 {item.step.evidence_ids?.length}</span>}
      </header>
      {item.seen && <p className={styles.seen} data-kind="vision-echo">{item.seen}</p>}
      <p className={styles.instruction}>{item.step.instruction}</p>
      <p className={styles.expected}><span>预期结果</span>{item.step.expected_result}</p>
      {item.step.caution && <p className={styles.caution} role="note">⚠ {item.step.caution}</p>}
      {answered ? (
        <>
          <p className={styles.answered}>您的反馈：{LABEL[answered]}{item.note ? `（${item.note}）` : ''}</p>
          {recorded.length > 0 && <p className={styles.observed} data-kind="observation-recorded">观察结果：{recorded.join('；')}</p>}
        </>
      ) : (
        <div className={styles.feedback}>
          {observations.map((obs) => (
            <fieldset key={obs.observation_id} className={styles.observation} data-kind="observation" disabled={!active || disabled}>
              <legend>{obs.question}</legend>
              {obs.options.map((opt) => (
                <label key={opt.option_id}>
                  <input
                    type="radio"
                    name={`${item.card_id}:${obs.observation_id}`}
                    value={opt.option_id}
                    checked={answers[obs.observation_id] === opt.option_id}
                    onChange={() => setAnswers((prev) => ({ ...prev, [obs.observation_id]: opt.option_id }))}
                  />
                  {opt.label}
                </label>
              ))}
            </fieldset>
          ))}
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="可补充说明（选填）" aria-label="补充说明" disabled={!active || disabled} />
          <div className={styles.feedbackButtons}>
            {(Object.keys(LABEL) as Feedback[]).map((k) => (
              <button key={k} type="button" data-feedback={k} disabled={!active || disabled} onClick={() => submit(k)}>{LABEL[k]}</button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
