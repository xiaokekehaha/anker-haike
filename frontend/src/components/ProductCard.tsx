import type { ProductCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

type Props = { item: ProductCardItem; active: boolean; disabled?: boolean; onSelect: (sku: string) => void };

/** 产品确认卡（票 21）：候选按钮组；in_scope=false 标「本期不支持」；选中后 disabled 并显示所选项。 */
export function ProductCard({ item, active, disabled, onSelect }: Props) {
  const chosen = item.selected_sku ?? null;
  return (
    <section className={styles.card} data-kind="product_card" aria-label="请确认您的产品">
      <header className={styles.cardHead}><strong>请确认是哪一台设备</strong>{chosen && <span className={styles.doneTag}>已选择</span>}</header>
      <ul className={styles.candidates}>
        {item.candidates.map((c) => (
          <li key={c.sku}>
            <button
              type="button"
              className={styles.candidate}
              data-selected={chosen === c.sku || undefined}
              disabled={!active || disabled || chosen !== null}
              onClick={() => onSelect(c.sku)}
            >
              {c.image ? <img src={c.image} alt="" /> : <span className={styles.candidateIcon} aria-hidden="true">{c.in_scope ? '🤖' : '📦'}</span>}
              <span className={styles.candidateName}>{c.name}</span>
              <span className={styles.candidateMeta}>{c.in_scope ? c.category : '本期不支持'}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
