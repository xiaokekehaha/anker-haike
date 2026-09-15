import { useState } from 'react';
import type { ContextCardItem } from '../types/snapshot';
import styles from './Cards.module.css';

const labels: Record<string, string> = { region_purchase: '购买地', region_use: '使用地', channel: '购买渠道', platform: '平台' };
const values: Record<string, string> = { CN: '中国', EU: '欧盟', DE: '德国', FR: '法国', IT: '意大利', ES: '西班牙', NL: '荷兰', UK: '英国', US: '美国', official_store: '官方渠道', platform_store: '平台店铺', authorized_dealer: '授权经销商', unauthorized_dealer: '非授权经销商' };
export function ContextCard({ item, active, disabled, onConfirm }: { item: ContextCardItem; active: boolean; disabled?: boolean; onConfirm: (fields: Record<string, string>) => void }) {
  const [fields, setFields] = useState<Record<string, string>>({ ...item.prefilled, ...item.confirmed_fields });
  const locked = !active || disabled || !!item.confirmed_fields;
  const missing = item.fields.filter(key => key in labels);
  const known = Object.keys(labels).filter(key => !missing.includes(key) && fields[key]);
  return <section className={styles.card} aria-label="确认服务信息">
    <header className={styles.cardHead}><strong>确认服务信息</strong>{item.confirmed_fields && <span className={styles.doneTag}>已确认</span>}</header>
    {known.length > 0 && <dl className={styles.fields}>{known.map(key => <div key={key}>
      <dt>{labels[key]}</dt><dd>{values[fields[key] ?? ''] ?? fields[key]}{item.sources?.[key] === 'receipt' && <small>来自已核实订单</small>}</dd>
    </div>)}</dl>}
    {!item.confirmed_fields && <p>请补充{missing.map(key => labels[key]).join('、')}，以核对适用政策。</p>}
    <form onSubmit={e => { e.preventDefault(); onConfirm(fields); }}>
      <dl className={styles.fields}>{missing.map(key => <div key={key}>
        <dt><label htmlFor={`${item.card_id}-${key}`}>{labels[key]}</label></dt>
        <dd><input id={`${item.card_id}-${key}`} list={`${item.card_id}-${key}-choices`} required={key !== 'platform'} value={fields[key] ?? ''} disabled={locked || item.sources?.[key] === 'receipt'} placeholder={key.startsWith('region') ? '例如：中国、德国、英国' : '请选择或填写'} onChange={e => setFields({ ...fields, [key]: e.target.value })} />
          <datalist id={`${item.card_id}-${key}-choices`}>{item.choices?.[key]?.map(value => <option key={value} value={value}>{values[value] ?? value}</option>)}</datalist>
        </dd>
      </div>)}</dl>
      <div className={styles.feedbackButtons}><button disabled={locked}>确认信息</button></div>
    </form>
  </section>;
}
