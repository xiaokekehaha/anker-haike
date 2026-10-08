import { useState } from 'react';
import type { ReceiptCardItem, ReceiptFields } from '../types/snapshot';
import styles from './Cards.module.css';

type Field = 'order_no' | 'seller' | 'country' | 'purchase_date' | 'amount';
const LABELS: Record<Field, string> = { order_no: '订单号', seller: '购买商家', country: '购买国家', purchase_date: '购买日期', amount: '金额' };
type Props = { item: ReceiptCardItem; active: boolean; disabled?: boolean; onConfirm: (fields: ReceiptFields, edited: Field[]) => void; onSkip: (reason: 'none' | 'unreadable' | 'later') => void };

/** 凭证确认卡（票 40 前端）：字段可编辑，confidence < 0.7 标黄；确认 / 跳过。 */
export function ReceiptCard(props: Props) {
  const { item } = props;
  // 相同卡片重放保留草稿；权威字段/版本变化时重建编辑器，避免沿用旧 OCR 值。
  const revision = JSON.stringify([item.card_id, item.version, ...Object.keys(LABELS).map(k => item.fields[k as Field] ?? null)]);
  return <ReceiptFieldsEditor key={revision} {...props} />;
}

function ReceiptFieldsEditor({ item, active, disabled, onConfirm, onSkip }: Props) {
  const [fields, setFields] = useState<ReceiptFields>({ ...item.fields });
  const done = item.confirmed_fields || item.skipped_reason;
  const displayed = item.confirmed_fields ?? fields;
  const edited = (Object.keys(LABELS) as Field[]).filter((k) => (fields[k] ?? '') !== (item.fields[k] ?? ''));
  return (
    <section className={styles.card} data-kind="receipt_card" aria-label="购买凭证信息">
      <header className={styles.cardHead}><strong>请核对购买凭证信息</strong>{done && <span className={styles.doneTag}>{item.skipped_reason ? '已跳过' : '已确认'}</span>}</header>
      <dl className={styles.fields}>
        {(Object.keys(LABELS) as Field[]).map((k) => {
          const conf = item.confidence?.[k];
          const low = typeof conf === 'number' && conf < 0.7;
          const unreadable = item.unreadable?.includes(k);
          return (
            <div key={k} data-low={low || undefined} data-unreadable={unreadable || undefined}>
              <dt>{LABELS[k]}{low && <span className={styles.lowTag}>置信度低</span>}{unreadable && <span className={styles.lowTag}>未识别</span>}</dt>
              <dd>
                <input value={displayed[k] ?? ''} disabled={!active || disabled || !!done} aria-label={LABELS[k]} onChange={(e) => setFields({ ...fields, [k]: e.target.value || null })} />
              </dd>
            </div>
          );
        })}
      </dl>
      {!done && (
        <div className={styles.feedbackButtons}>
          <button type="button" disabled={!active || disabled} onClick={() => onConfirm(fields, edited)}>确认</button>
          <button type="button" disabled={!active || disabled} onClick={() => onSkip('unreadable')}>看不清，跳过</button>
          <button type="button" disabled={!active || disabled} onClick={() => onSkip('later')}>稍后再提供</button>
        </div>
      )}
    </section>
  );
}
