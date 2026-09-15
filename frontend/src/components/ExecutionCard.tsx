import type { ExecutionCardItem } from '../types/snapshot';
import styles from './Cards.module.css';
export function ExecutionCard({ item }: { item: ExecutionCardItem }) {
  return <section className={styles.card} aria-label="办理回执">
    <header className={styles.cardHead}><strong>{item.status === 'succeeded' ? '申请已提交' : '本次申请未完成'}</strong></header>
    {item.receipt.service_order_no && <p>服务单号：<strong>{item.receipt.service_order_no}</strong></p>}
    <p>{item.receipt.next_step}</p><small>来源：{item.receipt.source}</small>
    <details><summary>回执标识</summary><code>{item.idempotency_key}</code></details>
  </section>;
}
