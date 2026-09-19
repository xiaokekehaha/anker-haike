import type { ToolItem } from '../types/snapshot';
import styles from './Cards.module.css';

const NAMES: Record<string, string> = { 'knowledge.search': '检索知识库', vision: '识别图片', 'diagnose.vision': '识别图片', 'logistics.query': '查询物流', 'order.lookup': '查询订单', 'warranty.lookup': '查询保修', 'replacement.create': '创建换货单' };

/** 工具行（票 28）：系统行样式；started 转圈、finished 打钩、failed 标红但流程继续。 */
export function ToolRow({ item }: { item: ToolItem }) {
  const label = NAMES[item.name] ?? item.name;
  const icon = item.status === 'started' ? '⟳' : item.status === 'finished' ? '✓' : '!';
  return (
    <div className={`${styles.sysRow} ${styles.toolRow}`} data-status={item.status} role="status" aria-live="polite">
      <span className={styles.toolIcon} aria-hidden="true">{icon}</span>
      <span className={styles.toolName}>{label}</span>
      <span className={styles.toolSummary}>{item.summary ?? (item.status === 'started' ? '进行中…' : '')}</span>
    </div>
  );
}
