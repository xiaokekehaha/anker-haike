import type { SessionState } from './types';
import type { EscalationSummary, EvidenceItem, Feedback, HandoffStatus, TimelineItem } from '../types/snapshot';
import { CASE_LABELS, caseStatusOf, progressFor } from './progress';
import { PRODUCT_CATEGORIES } from '../components/ChatPane';

/** 客户可见的「服务方式」：只说策略的人话，不说情绪等级（等级对客户标注会激化情绪）。 */
export const STRATEGY_LABELS: Record<string, string> = {
  normal: '常规处理',
  reassure_first: '先安抚，再排查',
  reassure_and_shorten: '先安抚，步骤尽量少',
  direct_resolution: '直接给方案',
  de_escalate_and_offer_human: '降温处理，随时可转人工',
};

/** 人工处理的真实状态：prepared 只是整理好了记录，不能显示成「已接入」。 */
export const HANDOFF_LABELS: Record<HandoffStatus, string> = {
  prepared: '已整理记录，尚未接入人工',
  requested: '已发起人工请求，等待接单',
  accepted: '人工已接单',
  failed: '人工接入失败',
  cancelled: '人工请求已取消',
};

export const FEEDBACK_LABELS: Record<Feedback, string> = { solved: '解决了', not_solved: '还没解决', cannot_do: '做不到' };

export type RecordStep = { card_id: string; no: number; title: string; feedback: Feedback | null; note: string | null; pending: boolean };

export type ServiceRecord = {
  product: { name: string; category: string | null } | null;
  problem: string | null;
  strategy: string | null;
  route: { steps: { key: string; label: string; hint: string }[]; active: number };
  steps: RecordStep[];
  evidence: EvidenceItem[];
  primary: string[];
  caseLabel: string | null;
  externalRefs: Record<string, string>;
  handoff: HandoffStatus | null;
  summary: EscalationSummary | null;
};

const CATEGORY_LABEL = new Map<string, string>(PRODUCT_CATEGORIES.map((c) => [c.key, c.label]));
const REF_LABELS: Record<string, string> = { order_no: '订单号', service_order_no: '服务单号', tracking_no: '物流单号' };

function last<T extends TimelineItem['kind']>(timeline: TimelineItem[], kind: T): Extract<TimelineItem, { kind: T }> | null {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const item = timeline[i]!;
    if (item.kind === kind) return item as Extract<TimelineItem, { kind: T }>;
  }
  return null;
}

/** 服务记录面板的数据：全部从 timeline 派生，不另建状态；快照恢复后结果一致。 */
export function deriveRecord(state: SessionState): ServiceRecord {
  const { timeline } = state;
  const summaryItem = last(timeline, 'escalation_summary');
  const summary = summaryItem?.summary ?? null;

  let product: ServiceRecord['product'] = null;
  for (let i = timeline.length - 1; i >= 0 && !product; i--) {
    const item = timeline[i]!;
    if (item.kind === 'product_card' && item.selected_sku) {
      const chosen = item.candidates.find((c) => c.sku === item.selected_sku);
      if (chosen) product = { name: chosen.name, category: CATEGORY_LABEL.get(chosen.category) ?? chosen.category };
    }
  }
  if (!product && summary?.product) product = { name: summary.product, category: null };

  const firstUser = timeline.find((t): t is Extract<TimelineItem, { kind: 'user_message' }> => t.kind === 'user_message');
  const problem = summary?.problem ?? firstUser?.text ?? null;

  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const steps: RecordStep[] = timeline.flatMap((t) => t.kind === 'step_card'
    ? [{ card_id: t.card_id, no: t.step.step_no, title: t.step.title, feedback: t.feedback ?? null, note: t.note ?? null, pending: t.card_id === pendingCard }]
    : []);

  // 同一条依据会随每次检索重复下发；按 evidence_id 去重，保留首次出现的位置
  const seen = new Set<string>();
  const evidence = timeline.filter((t): t is Extract<TimelineItem, { kind: 'evidence' }> => t.kind === 'evidence').flatMap((t) => t.items)
    .filter((e) => { if (seen.has(e.evidence_id)) return false; seen.add(e.evidence_id); return true; });
  const primary = timeline.flatMap((t) => (t.kind === 'step_card' && t.step.primary_evidence_id ? [t.step.primary_evidence_id] : []));

  const caseStatus = caseStatusOf(timeline, state.activeIssueId);
  const caseItem = last(timeline, 'case_changed');
  const externalRefs: Record<string, string> = {};
  for (const [key, value] of Object.entries(caseItem?.external_refs ?? {})) if (value) externalRefs[REF_LABELS[key] ?? key] = String(value);

  return {
    product,
    problem,
    strategy: summary ? STRATEGY_LABELS[summary.emotion.strategy] ?? null : null,
    route: progressFor(state.stage, caseStatus),
    steps,
    evidence,
    primary,
    caseLabel: caseStatus ? CASE_LABELS[caseStatus] ?? caseStatus : null,
    externalRefs,
    handoff: summaryItem?.handoff_status ?? (summaryItem ? 'prepared' : null),
    summary,
  };
}
