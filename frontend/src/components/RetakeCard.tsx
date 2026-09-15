import type { RetakeCardItem } from '../types/snapshot';
import styles from './Cards.module.css';
export function RetakeCard({ item, active, disabled, onSkip }: { item: RetakeCardItem; active: boolean; disabled?: boolean; onSkip: () => void }) {
  return <section className={styles.card} aria-label="补拍照片"><strong>这张照片还不够清晰</strong>
    <p>{item.reasons.join('；')}</p><ul>{item.guidance.map((text, i) => <li key={i}>{text}</li>)}</ul>
    <p>可在下方重新上传照片，也可以继续文字排查。</p>
    <div className={styles.feedbackButtons}><button disabled={!active || disabled || item.skipped} onClick={onSkip}>{item.skipped ? '已跳过补拍' : '跳过，继续文字排查'}</button></div>
  </section>;
}
