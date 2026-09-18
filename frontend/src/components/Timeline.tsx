import type { ReactNode } from 'react';
import { ContextCard } from './ContextCard';
import { ProposalCard } from './ProposalCard';
import { ExecutionCard } from './ExecutionCard';
import { RetakeCard } from './RetakeCard';
import { RatingCard } from './RatingCard';
import { CaseStatus } from './CaseStatus';
import type { SessionState } from '../state/types';
import type { TimelineItem } from '../types/snapshot';
import { AssistantBubble } from './AssistantBubble';
import { ObservationCard } from './ObservationCard';
import { ProductCard } from './ProductCard';
import { ReceiptCard } from './ReceiptCard';
import { StepCard } from './StepCard';
import { SummaryCard } from './SummaryCard';
import { ToolRow } from './ToolRow';
import { UserBubble } from './UserBubble';
import styles from './Cards.module.css';

type ActionKind = 'select_product' | 'step_feedback' | 'answer_observation' | 'confirm_receipt' | 'skip_receipt' | 'confirm_context' | 'confirm_proposal' | 'decline_proposal' | 'skip_retake' | 'rate_satisfaction';
type OnAction = (kind: ActionKind, payload: Record<string, unknown>) => void;

type Props = {
  state: SessionState;
  onAction: OnAction;
  /** 步骤卡悬停时引用的 evidence_ids（联动记录面板高亮） */
  onHover?: (ids: string[]) => void;
  /** 待反馈卡片由 dock 渲染，流里只留一行指针 */
  dockPending?: boolean;
};

type CardItem = Extract<TimelineItem, { card_id: string }>;

/** 待办卡的一行指针文案（流里）。 */
const POINTER: Partial<Record<TimelineItem['kind'], (item: CardItem) => string>> = {
  step_card: (item) => item.kind === 'step_card' ? `步骤 ${item.step.step_no} · ${item.step.title}` : '',
  product_card: () => '请确认是哪一台设备',
  observation_card: () => '选择最接近的情况',
  receipt_card: () => '核对购买凭证信息',
  context_card: () => '确认服务信息',
  proposal_card: () => '选择售后方案',
  retake_card: () => '补拍照片',
  rating_card: () => '评价本次服务',
};

function renderCard(item: CardItem, active: boolean, disabled: boolean, onAction: OnAction, onHover?: (ids: string[]) => void, outdated = false) {
  switch (item.kind) {
    case 'product_card':
      return <ProductCard key={item.card_id} item={item} active={active} disabled={disabled} onSelect={(sku) => onAction('select_product', { sku })} />;
    case 'step_card':
      return <StepCard key={item.card_id} item={item} active={active} disabled={disabled} onHover={onHover} onFeedback={(feedback, note, observations) => onAction('step_feedback', { feedback, ...(note ? { note } : {}), ...(observations?.length ? { observations } : {}) })} />;
    case 'observation_card':
      return <ObservationCard key={item.card_id} item={item} active={active} disabled={disabled} onAnswer={(observation_id, option_id) => onAction('answer_observation', { observation_id, option_id })} />;
    case 'receipt_card':
      return <ReceiptCard key={item.card_id} item={item} active={active} disabled={disabled} onConfirm={(fields, edited) => onAction('confirm_receipt', { fields, edited })} onSkip={(reason) => onAction('skip_receipt', { reason })} />;
    case 'context_card':
      return <ContextCard key={item.card_id} item={item} active={active} disabled={disabled} onConfirm={(fields) => onAction('confirm_context', fields)} />;
    case 'proposal_card':
      return <ProposalCard key={item.card_id} item={item} active={active} disabled={disabled} onConfirm={(option_id) => onAction('confirm_proposal', { option_id })} onDecline={(reason) => onAction('decline_proposal', { reason })} />;
    case 'execution_card':
      return <ExecutionCard key={item.card_id} item={item} />;
    case 'retake_card':
      return <RetakeCard key={item.card_id} item={item} active={active} disabled={disabled} onSkip={() => onAction('skip_retake', { reason: 'skip' })} />;
    case 'rating_card':
      return <RatingCard key={item.card_id} item={item} active={active} disabled={disabled} onRate={(score, comment) => onAction('rate_satisfaction', { score, comment })} />;
    case 'case_changed':
      return <CaseStatus key={item.card_id} item={item} />;
    case 'escalation_summary':
      return <SummaryCard key={item.card_id} summary={item.summary} updatedAt={item.updated_at} revision={item.revision} handoffStatus={item.handoff_status} outdated={outdated} />;
    default:
      return null;
  }
}

function pendingOf(state: SessionState): CardItem | null {
  const id = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  if (!id) return null;
  return (state.timeline.find((t): t is CardItem => 'card_id' in t && t.card_id === id) ?? null);
}

/** 停靠在输入框上方的待办卡：只有 pendingInput 指向的卡可交互。 */
export function PendingCard({ state, onAction, onHover }: { state: SessionState; onAction: OnAction; onHover?: (ids: string[]) => void }) {
  const item = pendingOf(state);
  if (!item) return null;
  return <div className={styles.dockCard} data-testid="pending-card">{renderCard(item, true, state.pendingActionId !== null, onAction, onHover)}</div>;
}

const FIVE_MINUTES = 5 * 60 * 1000;
function timeLabel(at: string): string {
  const d = new Date(at);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const hm = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  return sameDay ? `今天 ${hm}` : `${d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${hm}`;
}

/** 按 timeline 渲染（05 §3）。时间戳按 5 分钟分组成分隔行；连续助手消息合并头像；工具 / 动作 / 案件变更走系统行；来源不进流，由记录面板承载。 */
export function Timeline({ state, onAction, onHover, dockPending = false }: Props) {
  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const busy = state.pendingActionId !== null;
  const nodes: ReactNode[] = [];
  let lastTime: number | null = null;
  let prevKind: TimelineItem['kind'] | null = null;

  for (const item of state.timeline) {
    if (item.kind === 'evidence') continue;
    const at = 'at' in item && item.at ? Date.parse(item.at) : NaN;
    if (!Number.isNaN(at) && (lastTime === null || at - lastTime >= FIVE_MINUTES)) {
      nodes.push(<div key={`t-${at}-${nodes.length}`} className={styles.timeSep}>{timeLabel(item.at as string)}</div>);
      lastTime = at;
    }
    switch (item.kind) {
      case 'user_message':
        nodes.push(<UserBubble key={item.id} sessionId={state.id ?? ''} text={item.text} images={item.images} imageIds={item.image_ids} />);
        break;
      case 'assistant_message':
        nodes.push(<AssistantBubble key={item.message_id} item={item} cont={prevKind === 'assistant_message'} />);
        break;
      case 'action':
        nodes.push(<div key={item.id} className={styles.sysRow}>{item.label}</div>);
        break;
      case 'tool':
        nodes.push(<ToolRow key={item.tool_id} item={item} />);
        break;
      default: {
        const active = pendingCard === item.card_id;
        if (dockPending && active) {
          const label = POINTER[item.kind]?.(item) ?? '等待你的操作';
          nodes.push(<div key={item.card_id} className={styles.pointer} data-testid="pending-pointer"><span>{label}</span><span>等待你的反馈 ↓</span></div>);
        } else {
          const outdated = item.kind === 'escalation_summary' && state.timeline.some((t) => t.kind === 'escalation_summary' && t.summary_id === item.summary_id && t.revision > item.revision);
          nodes.push(renderCard(item, active, busy, onAction, onHover, outdated));
        }
      }
    }
    prevKind = item.kind;
  }
  return <div className={styles.timeline} aria-live="polite">{nodes}</div>;
}
