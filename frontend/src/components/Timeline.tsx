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

type Props = {
  state: SessionState;
  onAction: (kind: 'select_product' | 'step_feedback' | 'confirm_receipt' | 'skip_receipt', payload: Record<string, unknown>) => void;
};

/** 按 timeline 渲染（05 §3）；只有 pendingInput 指向的卡片可交互，其余置为历史。 */
export function Timeline({ state, onAction }: Props) {
  const [hover, setHover] = useState<string[]>([]);
  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const busy = state.pendingActionId !== null;
  const evidence = state.timeline.filter((t): t is Extract<TimelineItem, { kind: 'evidence' }> => t.kind === 'evidence').flatMap((t) => t.items);
  return (
    <div className={styles.timeline} aria-live="polite">
      {state.timeline.map((item, i) => {
        switch (item.kind) {
          case 'user_message':
            return <UserBubble key={item.id} sessionId={state.id ?? ''} text={item.text} images={item.images} imageIds={item.image_ids} />;
          case 'assistant_message':
            return <AssistantBubble key={item.message_id} item={item} />;
          case 'tool':
            return <ToolRow key={item.tool_id} item={item} />;
          case 'evidence':
            return <EvidenceDrawer key={`ev-${i}`} items={item.items} highlight={hover} />;
          case 'product_card':
            return <ProductCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onSelect={(sku) => onAction('select_product', { sku })} />;
          case 'step_card':
            return <StepCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onHover={setHover} onFeedback={(feedback, note) => onAction('step_feedback', note ? { feedback, note } : { feedback })} />;
          case 'receipt_card':
            return <ReceiptCard key={item.card_id} item={item} active={pendingCard === item.card_id} disabled={busy} onConfirm={(fields, edited) => onAction('confirm_receipt', { fields, edited })} onSkip={(reason) => onAction('skip_receipt', { reason })} />;
          case 'escalation_summary':
            return <SummaryCard key={item.card_id} summary={item.summary} />;
          default:
            return null;
        }
      })}
      {evidence.length === 0 && null}
    </div>
  );
}
