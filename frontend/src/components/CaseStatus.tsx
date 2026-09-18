import type { CaseStatusItem } from '../types/snapshot';
import styles from './Cards.module.css';
import { CASE_LABELS } from '../state/progress';
export { CASE_LABELS } from '../state/progress';
const REFS: Record<string, string> = { order_no: '订单号', service_order_no: '服务单号', tracking_no: '物流单号' };
/** 案件状态变更：一行系统行；单号与原因放 title，详情在服务记录面板。 */
export function CaseStatus({ item }: { item: CaseStatusItem }) {
  const refs = Object.entries(item.external_refs ?? {}).map(([key, value]) => `${REFS[key] ?? key} ${value}`).join(' · ');
  return <div className={styles.sysRow} aria-label="案件进度" title={[item.reason, refs].filter(Boolean).join('；')}>
    <span>{CASE_LABELS[item.status] ?? item.status}</span>{item.priority === 'high' && <span className={styles.lowTag}>优先处理</span>}
  </div>;
}
