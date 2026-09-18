import { useState } from 'react';
import type { SessionState } from '../state/types';
import { deriveRecord, FEEDBACK_LABELS, HANDOFF_LABELS } from '../state/record';
import { EvidenceDrawer } from './EvidenceDrawer';
import { summaryToText } from './SummaryCard';
import styles from './RecordPanel.module.css';

type Props = {
  state: SessionState;
  /** 当前悬停步骤卡引用的 evidence_ids，联动高亮依据 */
  highlight?: string[];
  busy?: boolean;
  onRequestHuman?: () => void;
  onNewIssue?: () => void;
  onResumeIssue?: (issueId: string) => void;
};

/** 服务记录面板（方案 A）：客服工单的客户侧投影，产品 / 问题 / 进度 / 已尝试 / 依据 / 案件随会话实时更新。 */
export function RecordPanel({ state, highlight = [], busy = false, onRequestHuman, onNewIssue, onResumeIssue }: Props) {
  const record = deriveRecord(state);
  const [copied, setCopied] = useState(false);
  const empty = state.timeline.length === 0;
  const tried = record.steps.filter((s) => s.feedback).length;
  const lockIssue = busy || !!state.activeRun;

  async function copy() {
    if (!record.summary) return;
    try {
      await navigator.clipboard.writeText(summaryToText(record.summary));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { setCopied(false); }
  }

  return (
    <div className={styles.panel} data-testid="record-panel">
      <section>
        <h2 className={styles.heading}>服务记录</h2>
        {empty ? (
          <p className={styles.empty}>开始对话后，这里会记录产品、问题和每一步的结果，转人工时可以直接复制。</p>
        ) : (
          <dl className={styles.kv}>
            <dt>产品</dt><dd>{record.product ? <>{record.product.name}{record.product.category && <small>{record.product.category}</small>}</> : <span className={styles.muted}>待确认</span>}</dd>
            <dt>问题</dt><dd>{record.problem ?? <span className={styles.muted}>待描述</span>}</dd>
            {record.strategy && <><dt>服务方式</dt><dd>{record.strategy}</dd></>}
          </dl>
        )}
      </section>

      {state.issues.length > 1 && onResumeIssue && (
        <section>
          <h2 className={styles.heading}>问题</h2>
          <select className={styles.select} aria-label="选择要继续的问题" value={state.activeIssueId ?? ''} disabled={lockIssue} onChange={(e) => onResumeIssue(e.target.value)}>
            {state.issues.map((issue) => <option key={issue.issue_id} value={issue.issue_id}>{issue.title || '待描述的问题'}</option>)}
          </select>
        </section>
      )}

      <section>
        <h2 className={styles.heading}>进度</h2>
        <ol className={styles.route} aria-label="处理进度">
          {record.route.steps.map((step, i) => {
            const active = i === record.route.active;
            return (
              <li key={step.key} data-state={active ? 'active' : 'idle'} aria-current={active ? 'step' : undefined}>
                <span className={styles.routeLabel}>{step.label}<small>{step.hint}</small></span>
              </li>
            );
          })}
        </ol>
      </section>

      {record.steps.length > 0 && (
        <section>
          <h2 className={styles.heading}>已尝试 <span className={styles.count}>{tried} / {record.steps.length}</span></h2>
          <ol className={styles.tried}>
            {record.steps.map((s) => (
              <li key={s.card_id} data-pending={s.pending || undefined}>
                <span className={styles.mark} aria-hidden="true">{s.feedback === 'solved' ? '✓' : s.feedback ? '✕' : '○'}</span>
                <span>{s.title}{s.note && <small>{s.note}</small>}</span>
                <span className={styles.result} data-feedback={s.feedback ?? 'pending'}>{s.feedback ? FEEDBACK_LABELS[s.feedback] : '进行中'}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {record.evidence.length > 0 && (
        <section>
          <h2 className={styles.heading}>依据 <span className={styles.count}>{record.evidence.length} 条</span></h2>
          <EvidenceDrawer items={record.evidence} highlight={highlight} primary={record.primary} open />
        </section>
      )}

      {(record.caseLabel || record.handoff) && (
        <section>
          <h2 className={styles.heading}>案件</h2>
          {record.caseLabel && <p className={styles.status}><span className={styles.dot} aria-hidden="true" />{record.caseLabel}</p>}
          {Object.entries(record.externalRefs).map(([label, value]) => <p key={label} className={styles.ref}>{label}<code>{value}</code></p>)}
          {record.handoff && <p className={styles.handoff} data-status={record.handoff}>人工处理：{HANDOFF_LABELS[record.handoff]}</p>}
        </section>
      )}

      {!empty && (
        <section className={styles.actions}>
          {record.summary && <button type="button" className={styles.primary} onClick={() => void copy()}>{copied ? '已复制' : '复制排查记录'}</button>}
          {onRequestHuman && <button type="button" onClick={onRequestHuman}>请求人工</button>}
          {onNewIssue && <button type="button" disabled={lockIssue} onClick={onNewIssue}>新问题</button>}
        </section>
      )}
    </div>
  );
}
