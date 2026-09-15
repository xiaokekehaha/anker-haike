import { useState } from 'react';
import type { RatingCardItem } from '../types/snapshot';
import styles from './Cards.module.css';
export function RatingCard({ item, active, disabled, onRate }: { item: RatingCardItem; active: boolean; disabled?: boolean; onRate: (score: number, comment?: string) => void }) {
  const [score, setScore] = useState<number | null>(item.score ?? null);
  const [comment, setComment] = useState('');
  const locked = !active || disabled || !!item.score;
  return <section className={styles.card} aria-label="服务满意度"><strong>这次服务体验如何？</strong>
    <p>1 分很不满意，5 分很满意。可以稍后评价；评分不会自动结案。</p>
    <div className={styles.feedbackButtons} role="group" aria-label="选择评分">{[1, 2, 3, 4, 5].map(n => <button key={n} aria-pressed={score === n} disabled={locked} onClick={() => setScore(n)}>{n} 分</button>)}</div>
    <label className={styles.feedback}>意见（可选）<input value={comment} maxLength={2000} disabled={locked} onChange={e => setComment(e.target.value)} /></label>
    <div className={styles.feedbackButtons}><button disabled={locked || !score} onClick={() => score && onRate(score, comment || undefined)}>{item.score ? '已评价' : '提交评价'}</button></div>
  </section>;
}
