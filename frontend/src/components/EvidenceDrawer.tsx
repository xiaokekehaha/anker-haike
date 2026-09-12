import type { EvidenceItem } from '../types/snapshot';
import styles from './Cards.module.css';

const SOURCE: Record<string, string> = { kb_manual: '说明书 / 手册', kb_tickets: '历史工单', fault_card: '产品故障卡' };

/** 来源抽屉（票 28）：折叠列出片段；highlight 为当前步骤卡引用的 evidence_ids，联动高亮。 */
export function EvidenceDrawer({ items, highlight = [] }: { items: EvidenceItem[]; highlight?: string[] }) {
  if (items.length === 0) return null;
  const hl = new Set(highlight);
  return (
    <details className={styles.drawer} data-testid="evidence-drawer">
      <summary>来源 {items.length} 条{hl.size > 0 && <span className={styles.drawerHint}>（当前步骤引用 {items.filter((i) => hl.has(i.evidence_id)).length} 条）</span>}</summary>
      <ol className={styles.evidenceList}>
        {items.map((e) => (
          <li key={e.evidence_id} data-highlight={hl.has(e.evidence_id) || undefined} data-status={e.status}>
            <span className={styles.evidenceSource}>{SOURCE[e.source] ?? e.source}</span>
            <span className={styles.evidenceDoc}>{e.doc_id} · v{e.doc_version}{e.status === 'replay' ? ' · 演示回放' : ''}</span>
            <p>{e.snippet}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}
