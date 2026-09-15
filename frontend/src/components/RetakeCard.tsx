import type { RetakeCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

// reasons 是机器码（同时用于路由与统计），直接渲染会把 "too_dark" 这种字样摆到用户面前。
// 指引文案已由后端给出，这里只把「为什么」翻成一句人话。
const REASON_LABELS: Record<string, string> = {
  blurry: '照片有点模糊',
  too_dark: '光线偏暗',
  too_bright: '光线过强或反光',
  too_far: '拍得太远，部件太小',
  wrong_subject: '画面里不是这台设备的故障部件',
  occluded: '故障部件被挡住了',
};

export function RetakeCard({ item, active, disabled, onSkip }: { item: RetakeCardItem; active: boolean; disabled?: boolean; onSkip: () => void }) {
  const why = item.reasons.map((r) => REASON_LABELS[r] ?? r);
  return <section className={styles.card} aria-label="补拍照片"><strong>这张照片还不够清晰</strong>
    {why.length > 0 && <p>{why.join('；')}</p>}
    <ul>{item.guidance.map((text, i) => <li key={i}>{text}</li>)}</ul>
    <p>可在下方重新上传照片，也可以继续文字排查。</p>
    <div className={styles.feedbackButtons}><button disabled={!active || disabled || item.skipped} onClick={onSkip}>{item.skipped ? '已跳过补拍' : '跳过，继续文字排查'}</button></div>
  </section>;
}
