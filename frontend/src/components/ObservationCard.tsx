import type { ObservationCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

type Props = {
  item: ObservationCardItem;
  active: boolean;
  disabled?: boolean;
  onAnswer: (observationId: string, optionId: string) => void;
};

/** 判别问题卡：计划级观察题独立追问时的选项。与步骤卡里的 observations 用同一份定义，
 *  区别只是这里没有伴随的操作步骤，所以点一次即提交，不再要二次确认。
 *  kind=unknown 的选项是「答不上来」而不是一种现象，单独排在下面：它不写观察事实，
 *  只是告诉后端别再追问这道题。输入框始终可用，用户想打字描述也照旧受理。 */
export function ObservationCard({ item, active, disabled, onAnswer }: Props) {
  const chosen = item.chosen_option_id ?? null;
  const options = item.observation.options;
  const findings = options.filter((o) => o.kind !== 'unknown');
  const unknown = options.find((o) => o.kind === 'unknown') ?? null;
  const chosenLabel = options.find((o) => o.option_id === chosen)?.label ?? null;
  const lock = !active || disabled || chosen !== null;
  if (!active && chosen) {
    return (
      <div className={styles.stepCollapsed} data-kind="observation_card">
        <span>{item.observation.question}</span>
        <span className={styles.doneTag}>{chosenLabel}</span>
      </div>
    );
  }
  return (
    <section className={styles.card} data-kind="observation_card" aria-label="排查判别问题">
      <header className={styles.cardHead}>
        <strong>{item.observation.question}</strong>
        {chosen ? <span className={styles.doneTag}>已选择</span> : <span className={styles.sourceTag}>选一项，或直接打字描述</span>}
      </header>
      <ul className={styles.candidates}>
        {findings.map((o) => (
          <li key={o.option_id}>
            <button
              type="button"
              className={styles.candidate}
              data-option={o.option_id}
              data-selected={chosen === o.option_id || undefined}
              disabled={lock}
              onClick={() => onAnswer(item.observation.observation_id, o.option_id)}
            >
              <span className={styles.candidateName}>{o.label}</span>
            </button>
          </li>
        ))}
      </ul>
      {unknown && (
        <div className={styles.feedbackButtons}>
          <button
            type="button"
            data-option={unknown.option_id}
            data-selected={chosen === unknown.option_id || undefined}
            disabled={lock}
            onClick={() => onAnswer(item.observation.observation_id, unknown.option_id)}
          >
            {unknown.label}
          </button>
        </div>
      )}
    </section>
  );
}
