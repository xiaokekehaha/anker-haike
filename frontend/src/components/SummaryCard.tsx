import { useState } from 'react';
import type { EscalationSummary, ExecutedStep, Feedback } from '../types/snapshot';
import styles from './Cards.module.css';
import { HANDOFF_LABELS } from '../state/record';

const STATUS: Record<string, string> = {
  not_collected: '未收集', insufficient: '信息不足', order_verified: '订单已核实', order_product_mismatch: '订单与设备不一致',
  needs_manual_check: '需人工核实', channel_in_directory: '经销商在名录内', channel_unknown: '渠道未知',
};

const FEEDBACK_LABELS: Record<Feedback, string> = {
  solved: '已解决', not_solved: '已操作，仍有问题', cannot_do: '无法操作',
};

const stepText = (x: ExecutedStep) =>
  `${x.title}（${FEEDBACK_LABELS[x.feedback]}${x.observed?.length ? `；观察：${x.observed.join('、')}` : ''}）`;

const FACT_LABELS: Record<string, string> = {
  channel: '订单渠道', purchase_date: '购买日期', 'dealer.name': '经销商', authorized: '名录授权状态',
};

function receiptFacts(facts: Record<string, string>): string {
  const authorization: Record<string, string> = { true: '已授权', false: '未授权' };
  return Object.entries(facts).map(([key, value]) => {
    const display = key === 'authorized' ? (authorization[value] ?? value) : value;
    return `${FACT_LABELS[key] ?? key}：${display}`;
  }).join('；');
}

/** 与后端 summary_to_text 同款的可读文本（票 16 一键复制）。 */
export function summaryToText(s: EscalationSummary): string {
  return [
    `【产品】${s.product}`,
    `【问题】${s.problem}`,
    `【观察】${s.observations?.join('；') || '无'}`,
    `【假设】${s.hypotheses?.join('；') || '无'}`,
    `【排查记录】${s.steps?.map(stepText).join('；') || '无'}`,
    `【升级原因】${s.reason.rule_id}：${s.reason.text}`,
    `【情绪】${s.emotion.level ?? '未判断'} / ${s.emotion.strategy}`,
    `【凭证】${s.receipt.status}${s.receipt.next_step ? `，下一步：${s.receipt.next_step}` : ''}`,
    `【凭证核实事实】${receiptFacts(s.receipt.verified_facts ?? {}) || '无'}`,
    `【凭证待核实差异】${s.receipt.conflicts?.join('；') || '无'}`,
  ].join('\n');
}

export function SummaryCard({ summary, updatedAt, revision, handoffStatus = 'prepared', outdated = false }: { summary: EscalationSummary; updatedAt?: string; revision?: number; handoffStatus?: string; outdated?: boolean }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(summaryToText(summary));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <section className={styles.card} data-kind="escalation_summary" aria-label="转人工摘要">
      <header className={styles.cardHead}><strong>问题摘要已整理，可复制给人工客服</strong><button type="button" onClick={copy} className={styles.copyBtn}>{copied ? '已复制' : '一键复制'}</button></header>
      <p className={styles.handoffStatus} data-kind="handoff-status" data-status={handoffStatus}>人工处理：{HANDOFF_LABELS[handoffStatus as keyof typeof HANDOFF_LABELS] ?? handoffStatus}</p>
      {revision && <small>第 {revision} 版{outdated ? ' · 此为当时记录，已有更新' : ''}</small>}
      {updatedAt && <small className={styles.answered}>{new Date(updatedAt).toLocaleString('zh-CN')}</small>}
      <dl className={styles.summary}>
        <div><dt>产品</dt><dd>{summary.product}</dd></div>
        <div><dt>问题</dt><dd>{summary.problem}</dd></div>
        <div><dt>观察</dt><dd>{summary.observations?.length ? summary.observations.join('；') : '无'}</dd></div>
        <div><dt>假设</dt><dd>{summary.hypotheses?.length ? summary.hypotheses.join('；') : '无'}</dd></div>
        <div><dt>排查记录</dt><dd>{summary.steps?.length ? summary.steps.map(stepText).join('；') : '无'}</dd></div>
        <div><dt>结束原因</dt><dd data-kind="end-reason">{summary.reason.text}<small> · 规则码 <code>{summary.reason.rule_id}</code>{summary.reason.cause ? ` · ${summary.reason.cause}` : ''}</small></dd></div>
        <div><dt>凭证状态</dt><dd>{STATUS[summary.receipt.status] ?? summary.receipt.status}{summary.receipt.next_step ? ` · 下一步：${summary.receipt.next_step}` : ''}</dd></div>
        {Object.keys(summary.receipt.verified_facts ?? {}).length > 0 && <div><dt>凭证核实事实</dt><dd>{receiptFacts(summary.receipt.verified_facts ?? {})}</dd></div>}
        {!!summary.receipt.conflicts?.length && <div><dt>凭证待核实差异</dt><dd>{summary.receipt.conflicts.join('；')}</dd></div>}
      </dl>
    </section>
  );
}
