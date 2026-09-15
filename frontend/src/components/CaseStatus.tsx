import type { CaseStatusItem } from '../types/snapshot';
import styles from './Cards.module.css';
import { CASE_LABELS } from '../state/progress';
export { CASE_LABELS } from '../state/progress';
export function CaseStatus({ item }: { item: CaseStatusItem }) {
  return <section className={styles.card} aria-label="案件进度"><header className={styles.cardHead}><strong>{CASE_LABELS[item.status] ?? item.status}</strong>{item.priority === 'high' && <span className={styles.lowTag}>优先处理</span>}</header>
    <p>{item.reason}</p>{Object.entries(item.external_refs ?? {}).map(([key, value]) => <p key={key}>{{ order_no: '订单号', service_order_no: '服务单号', tracking_no: '物流单号' }[key] ?? key}：{value}</p>)}
    <small>更新时间：{new Date(item.updated_at).toLocaleString('zh-CN')}</small>
  </section>;
}
