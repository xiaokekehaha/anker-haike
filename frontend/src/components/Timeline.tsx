import { ContextCard } from './ContextCard';
import { ProposalCard } from './ProposalCard';
import { ExecutionCard } from './ExecutionCard';
import { RetakeCard } from './RetakeCard';
import { RatingCard } from './RatingCard';
import { CaseStatus } from './CaseStatus';
import { useState } from 'react';
import type { SessionState } from '../state/types';
import type { TimelineItem } from '../types/snapshot';
import { AssistantBubble } from './AssistantBubble';
import { EvidenceDrawer } from './EvidenceDrawer';
import { ProductCard } from './ProductCard';
import { ReceiptCard } from './ReceiptCard';
import { StepCard } from './StepCard';
import { SummaryCard } from './SummaryCard';
import { ToolRow } from './ToolRow';
import { UserBubble } from './UserBubble';
import styles from './Cards.module.css';
import { MessageTime } from './MessageTime';

type Props = {
  state: SessionState;
  onAction: (kind: 'select_product' | 'step_feedback' | 'confirm_receipt' | 'skip_receipt' | 'confirm_context' | 'confirm_proposal' | 'decline_proposal' | 'skip_retake' | 'rate_satisfaction', payload: Record<string, unknown>) => void;
  onIssueAction?: (kind: 'new_issue' | 'resume_issue', issueId?: string) => void;
};

/** 按 timeline 渲染（05 §3）；只有 pendingInput 指向的卡片可交互，其余置为历史。 */
export function Timeline({ state, onAction, onIssueAction }: Props) {
  const [hover, setHover] = useState<string[]>([]);
  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const busy = state.pendingActionId !== null;
  const evidence = state.timeline.filter((t): t is Extract<TimelineItem, { kind: 'evidence' }> => t.kind === 'evidence').flatMap((t) => t.items);
  return (
    <div className={styles.timeline} aria-live="polite">
      {state.id && onIssueAction && <nav aria-label="会话中的问题" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {state.issues.length > 1 && <select aria-label="选择要继续的问题" value={state.activeIssueId ?? ''} disabled={busy || !!state.activeRun}
          onChange={e => onIssueAction('resume_issue', e.target.value)}>
          {state.issues.map(issue => <option key={issue.issue_id} value={issue.issue_id}>{issue.title || '待描述的问题'}</option>)}
        </select>}
        <button type="button" disabled={busy || !!state.activeRun} onClick={() => onIssueAction('new_issue')}>新问题</button>
      </nav>}
      {state.timeline.map((item, i) => {
        switch (item.kind) {
          case 'user_message':
            return <UserBubble key={item.id} sessionId={state.id ?? ''} text={item.text} images={item.images} imageIds={item.image_ids} at={item.at} />;
          case 'action':
            return <div key={item.id}><small>{item.label}</small><MessageTime at={item.at} /></div>;
          case 'assistant_message':
            return <AssistantBubble key={item.message_id} item={item} />;
          case 'tool':
            return <ToolRow key={item.tool_id} item={item} />;
          case 'evidence':
            return <EvidenceDrawer key={`ev-${i}`} items={item.items} highlight={hover} />;
          case 'product_card':
            return <ProductCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onSelect={(sku) => onAction('select_product', { sku })} />;
          case 'step_card':
            return <StepCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onHover={setHover} onFeedback={(feedback, note, observations) => onAction('step_feedback', { feedback, ...(note ? { note } : {}), ...(observations?.length ? { observations } : {}) })} />;
          case 'receipt_card':
            return <ReceiptCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onConfirm={(fields, edited) => onAction('confirm_receipt', { fields, edited })} onSkip={(reason) => onAction('skip_receipt', { reason })} />;
          case 'context_card':
            return <ContextCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onConfirm={fields => onAction('confirm_context', fields)} />;
          case 'proposal_card':
            return <ProposalCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onConfirm={option_id => onAction('confirm_proposal', { option_id })} onDecline={reason => onAction('decline_proposal', { reason })} />;
          case 'execution_card':
            return <ExecutionCard key={item.card_id} item={item} />;
          case 'retake_card':
            return <RetakeCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onSkip={() => onAction('skip_retake', { reason: 'skip' })} />;
          case 'rating_card':
            return <RatingCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onRate={(score, comment) => onAction('rate_satisfaction', { score, comment })} />;
          case 'case_changed':
            return <CaseStatus key={item.card_id} item={item} />;
          case 'escalation_summary':
            return <SummaryCard key={item.card_id} summary={item.summary} updatedAt={item.updated_at} revision={item.revision} handoffStatus={item.handoff_status} outdated={state.timeline.some(t => t.kind === 'escalation_summary' && t.summary_id === item.summary_id && t.revision > item.revision)} />;
          default:
            return null;
        }
      })}
      {evidence.length === 0 && null}
    </div>
  );
}
