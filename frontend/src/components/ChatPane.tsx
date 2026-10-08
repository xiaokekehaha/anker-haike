import { useState } from 'react';
import { type OfficialTicket, listOfficialTickets } from '../api/officialTickets';
import styles from './ChatPane.module.css';

// 品类与 config/products.yaml 对齐：只收主办方资料包里的三类产品（扫地机 / 吸奶器 / SoloCam 摄像头）。
// 点击发出的文字要能被 category_hint 的关键词认出；吸奶器与 SoloCam 品类下只有一款，品类即型号。
export const PRODUCT_CATEGORIES = [
  { key: 'robot_vacuum', label: '扫地机器人', supported: true },
  { key: 'breast_pump', label: '吸奶器', supported: true },
  { key: 'security_cam', label: '安防摄像头', supported: true },
] as const;

// 示例取自主办方真实工单（T18 荷兰语 App 报错、T55 英文 RMA、T1 物流、T45 经销商购买）。
export const STARTER_PROMPTS = [
  { text: 'Product Name: Omni E28\nProduct PN: T2352\nProblem Type: WARNING\nProblem Code: 3212-The mop is stuck.\nProblem Description: Rolling Mop Blockage. Please clean.', tag: 'App 报错' },
  { text: 'I have been using this breast pump for less than three weeks and the left pump will no longer suction. Order No: Anker016', tag: '故障 + 订单' },
  { text: 'The vacuum did not arrive. Only the replacement parts kit. Was the vacuum shipped? My order is Anker001', tag: '物流' },
  { text: '我的 S1 Pro 不吸了，明天家里要来客人，急！', tag: '同名消歧' },
] as const;

type Props = { onPick: (text: string) => void; onLoadTicket?: (ticket: OfficialTicket) => void; disabled?: boolean };

/** 首屏 intake：一句开场白 + 品类 chip + 示例。线上 Live Chat 的开场白要求「一条消息里同时给型号与问题」，这里照做。 */
export function ChatPane({ onPick, onLoadTicket, disabled }: Props) {
  const [tickets, setTickets] = useState<OfficialTicket[] | null>(null);
  // 展开时才拉列表：首屏不多发请求
  const loadList = () => {
    if (tickets === null) listOfficialTickets().then(setTickets).catch(() => setTickets([]));
  };
  return (
    <div className={styles.pane}>
      <p className={styles.eyebrow}>ANKER eufy · 售后服务 · 真正听懂，真正解决</p>
      <div className={styles.assistant}>
        <span className={styles.avatar} aria-hidden="true">✦</span>
        <div className={styles.bubble}>
          <p>你好，我是 Anker 智能售后助手。说说设备型号和遇到的问题，App 里的错误码、订单号也可以直接贴进来，我会陪你一步步处理。支持中文与英文、荷兰语、德语、法语、西班牙语。</p>
        </div>
      </div>

      <section className={styles.block} aria-labelledby="cat-title">
        <h3 id="cat-title">也可以先选产品<span>选填</span></h3>
        <ul className={styles.categories}>
          {PRODUCT_CATEGORIES.map((c) => (
            <li key={c.key}>
              <button type="button" disabled={disabled} data-supported onClick={() => onPick(`我的${c.label}出问题了：`)}>{c.label}</button>
            </li>
          ))}
        </ul>
      </section>

      <details className={styles.examples} open>
        <summary>不知道怎么说？看看真实工单示例</summary>
        <ul className={styles.starters}>
          {STARTER_PROMPTS.map((s) => (
            <li key={s.text}>
              <button type="button" disabled={disabled} onClick={() => onPick(s.text)}>
                <span className={styles.starterTag}>{s.tag}</span>
                <span>{s.text.split('\n').slice(-1)[0]}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>

      {onLoadTicket && (
        <details className={styles.examples} onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) loadList(); }}>
          <summary>载入主办方真实工单（演示 / 回归）</summary>
          {tickets === null ? <p className={styles.ticketHint}>加载中…</p> : tickets.length === 0 ? <p className={styles.ticketHint}>工单列表暂不可用</p> : (
            <select
              className={styles.ticketSelect}
              aria-label="选择主办方工单"
              disabled={disabled}
              value=""
              onChange={(e) => {
                const ticket = tickets.find((t) => t.id === e.target.value);
                if (ticket) onLoadTicket(ticket);
              }}
            >
              <option value="">选择 T1–T63，原文与附件图载入输入框…</option>
              {tickets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} · {t.scenario === 'shipping' ? '物流' : '排障'} · {t.product_name}{t.attachments.length ? ` · ${t.attachments.length} 图` : ''}
                </option>
              ))}
            </select>
          )}
        </details>
      )}
    </div>
  );
}
