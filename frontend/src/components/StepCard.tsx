import { useState } from 'react';
import type { StepAnswer, StepCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

type Feedback = 'solved' | 'not_solved' | 'cannot_do';
export type StepReply = { feedback?: Feedback; note?: string; answer?: StepAnswer };
type Props = {
  item: StepCardItem;
  active: boolean;
  disabled?: boolean;
  onReply: (reply: StepReply) => void;
  onHover?: (ids: string[]) => void;
};

const LABEL: Record<Feedback, string> = { solved: '解决了', not_solved: '还没解决', cannot_do: '做不到 / 跳过' };
const KIND_LABEL = { action: '步骤', question: '请回答', statement: '请查看', material_request: '请提供', handoff: '交人工' } as const;

function answeredText(item: StepCardItem): string | null {
  if (item.feedback) return `${LABEL[item.feedback]}${item.note ? `（${item.note}）` : ''}`;
  const a = item.answer;
  if (!a) return null;
  if (a.unavailable) return '暂时没有';
  return a.option ?? a.text ?? null;
}

/** 步骤卡（票 34 前端；2026-10-09 第二批按 kind 分型）：
 *  action 问「解决了 / 没解决 / 做不到」；question 给选项或短答；material_request 可上传或说暂时没有；
 *  statement 只需「知道了」。事实问题不用操作结果来答，标题与说明不计已操作。
 *  seen 是读图结果的隐式确认，排在操作之前单独一行。 */
export function StepCard({ item, active, disabled, onReply, onHover }: Props) {
  const [note, setNote] = useState('');
  const [text, setText] = useState('');
  const kind = item.step.kind ?? 'action';
  const answered = answeredText(item);
  const off = !active || disabled;
  if (!active && answered !== null) {
    return (
      <div className={styles.stepCollapsed} data-kind="step_card" data-step-kind={kind}>
        <span>{KIND_LABEL[kind]} {item.step.step_no}：{item.step.title}</span><span className={styles.doneTag}>{answered}</span>
      </div>
    );
  }
  const feedback = (fb: Feedback) => onReply({ feedback: fb, ...(note.trim() ? { note: note.trim() } : {}) });
  const answer = (a: StepAnswer) => onReply({ answer: a });
  let controls;
  if (answered !== null) {
    controls = <p className={styles.answered}>您的{kind === 'action' ? '反馈' : '回答'}：{answered}</p>;
  } else if (kind === 'question') {
    controls = (
      <div className={styles.feedback}>
        {(item.step.options?.length ?? 0) > 0 && (
          <div className={styles.feedbackButtons} role="group" aria-label="选项">
            {item.step.options!.map((o) => (
              <button key={o} type="button" data-option={o} disabled={off} onClick={() => answer({ option: o, text: null, unavailable: false })}>{o}</button>
            ))}
          </div>
        )}
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="或用几句话描述" aria-label="短答" disabled={off} />
        <div className={styles.feedbackButtons}>
          <button type="button" data-answer="text" disabled={off || !text.trim()} onClick={() => answer({ option: null, text: text.trim(), unavailable: false })}>提交回答</button>
        </div>
      </div>
    );
  } else if (kind === 'material_request') {
    controls = (
      <div className={styles.feedback}>
        <p className={styles.expected}><span>怎么提供</span>直接在下方输入框附上图片或视频链接发送；没有的话点「暂时没有」。</p>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="可补充说明（选填）" aria-label="材料说明" disabled={off} />
        <div className={styles.feedbackButtons}>
          <button type="button" data-answer="text" disabled={off || !text.trim()} onClick={() => answer({ option: null, text: text.trim(), unavailable: false })}>提交说明</button>
          <button type="button" data-answer="unavailable" disabled={off} onClick={() => answer({ option: null, text: null, unavailable: true })}>暂时没有</button>
        </div>
      </div>
    );
  } else if (kind === 'statement') {
    controls = (
      <div className={styles.feedbackButtons}>
        <button type="button" data-answer="ack" disabled={off} onClick={() => onReply({})}>知道了</button>
      </div>
    );
  } else {
    controls = (
      <div className={styles.feedback}>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="可补充说明（选填）" aria-label="补充说明" disabled={off} />
        <div className={styles.feedbackButtons}>
          {(Object.keys(LABEL) as Feedback[]).map((k) => (
            <button key={k} type="button" data-feedback={k} disabled={off} onClick={() => feedback(k)}>{LABEL[k]}</button>
          ))}
        </div>
      </div>
    );
  }
  return (
    <section className={styles.card} data-kind="step_card" data-step-kind={kind} data-pending={active && answered === null ? true : undefined} aria-label={`${KIND_LABEL[kind]} ${item.step.step_no}`} onMouseEnter={() => onHover?.(item.step.evidence_ids ?? [])} onMouseLeave={() => onHover?.([])}>
      <header className={styles.cardHead}>
        <strong>{KIND_LABEL[kind]} {item.step.step_no}：{item.step.title}</strong>
        {(item.step.evidence_ids?.length ?? 0) > 0 && <span className={styles.sourceTag} title="依据见右侧服务记录">依据 {item.step.evidence_ids?.length}</span>}
      </header>
      {item.seen && <p className={styles.seen} data-kind="vision-echo">{item.seen}</p>}
      {item.step.context && <p className={styles.context} data-kind="step-context">{item.step.context}</p>}
      {kind !== 'question' && <p className={styles.instruction}>{item.step.instruction}</p>}
      {(item.step.media?.length ?? 0) > 0 && (
        <ul className={styles.stepMedia} aria-label="官方图示">
          {item.step.media!.map((m) => (
            <li key={m.url}>
              {m.kind === 'image'
                ? <a href={m.url} target="_blank" rel="noreferrer"><img src={m.url} alt="官方操作图示" loading="lazy" /></a>
                : <a href={m.url} target="_blank" rel="noreferrer">{m.kind === 'video' ? '▶ 观看官方操作视频' : '查看官方说明'}</a>}
            </li>
          ))}
        </ul>
      )}
      {kind === 'action' && <p className={styles.expected}><span>预期结果</span>{item.step.expected_result}</p>}
      {item.step.caution && <p className={styles.caution} role="note">⚠ {item.step.caution}</p>}
      {controls}
    </section>
  );
}
