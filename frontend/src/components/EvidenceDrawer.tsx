import type { EvidenceItem } from '../types/snapshot';
import styles from './Cards.module.css';

const SOURCE: Record<string, string> = { kb_manual: '说明书 / 手册', kb_tickets: '历史工单', fault_card: '产品故障卡', approved_plan: '预写排障资料' };

function Item({ e, highlighted, primary }: { e: EvidenceItem; highlighted: boolean; primary?: boolean }) {
  return (
    <li data-highlight={highlighted || undefined} data-status={e.status} data-primary={primary || undefined}>
      <span className={styles.evidenceSource}>{SOURCE[e.source] ?? e.source}</span>
      <span className={styles.evidenceDoc}>{e.doc_id} · v{e.doc_version}{e.status === 'replay' ? ' · 演示回放' : ''}</span>
      <p>{e.snippet}</p>
    </li>
  );
}

/** 来源抽屉（票 28）：折叠列出片段；highlight 为当前步骤卡引用的 evidence_ids，联动高亮。
 *  primary 是各步骤的主引用——步骤引用的是同 doc 的宽集合，一步「清理滚刷」会把滤网、尘盒的
 *  命中一起带上，全部平铺会让「来源 5 条」里真正支撑这一步的那 1 条淹掉。所以主引用直接展开，
 *  其余折叠一层。 */
export function EvidenceDrawer({ items, highlight = [], primary = [], open = false }: { items: EvidenceItem[]; highlight?: string[]; primary?: string[]; open?: boolean }) {
  if (items.length === 0) return null;
  const hl = new Set(highlight);
  const pr = new Set(primary);
  const main = items.filter((i) => pr.has(i.evidence_id));
  const others = items.filter((i) => !pr.has(i.evidence_id));
  return (
    <details className={styles.drawer} data-testid="evidence-drawer" open={open || undefined}>
      <summary>来源 {items.length} 条{hl.size > 0 && <span className={styles.drawerHint}>（当前步骤引用 {items.filter((i) => hl.has(i.evidence_id)).length} 条）</span>}</summary>
      {main.length > 0 && (
        <ol className={styles.evidenceList} data-testid="evidence-primary">
          {main.map((e) => <Item key={e.evidence_id} e={e} highlighted={hl.has(e.evidence_id)} primary />)}
        </ol>
      )}
      {others.length > 0 && (main.length > 0 ? (
        <details className={styles.evidenceMore} data-testid="evidence-others">
          <summary>其他相关来源 {others.length} 条</summary>
          <ol className={styles.evidenceList}>
            {others.map((e) => <Item key={e.evidence_id} e={e} highlighted={hl.has(e.evidence_id)} />)}
          </ol>
        </details>
      ) : (
        <ol className={styles.evidenceList}>
          {others.map((e) => <Item key={e.evidence_id} e={e} highlighted={hl.has(e.evidence_id)} />)}
        </ol>
      ))}
    </details>
  );
}
