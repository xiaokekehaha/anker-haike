import type { Stage } from '../types/events';
import type { TimelineItem } from '../types/snapshot';

type Step = { key: string; label: string; hint: string };
const DIAGNOSIS: Step[] = [
  { key: 'understand', label: '理解需求', hint: '听懂问题与情绪' },
  { key: 'product', label: '确认产品', hint: '分清是哪台设备' },
  { key: 'diagnose', label: '定位故障', hint: '结合照片与知识库' },
  { key: 'guide', label: '分步排障', hint: '一次一步，反馈推进' },
  { key: 'result', label: '处理结果', hint: '查看结果或人工接续' },
];
const SERVICE: Step[] = [
  DIAGNOSIS[0]!,
  { key: 'context', label: '核实服务信息', hint: '补齐办理所需信息' },
  { key: 'proposal', label: '确认处理方案', hint: '查看费用、条件与依据' },
  { key: 'execution', label: '审核与办理', hint: '按确认后的方案处理' },
  { key: 'tracking', label: '跟踪办理进度', hint: '查看回执与收货进度' },
];
const QUERY: Step[] = [DIAGNOSIS[0]!, { key: 'query', label: '查询信息', hint: '读取对应订单的业务记录' }, { key: 'result', label: '返回查询结果', hint: '结果注明来源和时间' }];

export const CASE_LABELS: Record<string, string> = { open: '案件已建立', diagnosing: '核实问题中', proposing: '制定方案中', awaiting_confirmation: '等待确认', awaiting_approval: '等待人工审核', approved: '人工已批准', rejected: '人工未批准', executing: '办理中', executing_failed: '办理失败，可重试', tracking: '跟踪中', closed: '已结案', closed_unresolved: '暂未解决，已结束', reopened: '已重新受理', escalated_summary: '已整理交接资料' };

const STAGES: Record<Stage, { key: string; label: string; hint: string; flow: 'diagnosis' | 'service' | 'query' | 'result' }> = {
  intake: { ...DIAGNOSIS[0]!, flow: 'diagnosis' },
  disambiguate: { ...DIAGNOSIS[1]!, flow: 'diagnosis' },
  diagnose: { ...DIAGNOSIS[2]!, flow: 'diagnosis' },
  guide: { ...DIAGNOSIS[3]!, flow: 'diagnosis' },
  verify: { key: 'guide', label: '核对排障结果', hint: '根据反馈决定下一步', flow: 'diagnosis' },
  consult: { ...QUERY[1]!, flow: 'query' },
  context: { ...SERVICE[1]!, flow: 'service' },
  propose: { ...SERVICE[2]!, flow: 'service' },
  execute: { key: 'execution', label: '办理申请', hint: '以实际执行回执为准', flow: 'service' },
  awaiting_human: { key: 'execution', label: '等待人工审核', hint: '审核决定会回到本会话', flow: 'service' },
  track: { ...SERVICE[4]!, flow: 'service' },
  done: { key: 'result', label: '本轮已完成', hint: '可以继续追问或查看办理进度', flow: 'result' },
  escalate: { key: 'result', label: '人工接续', hint: '已整理问题记录，请查看接续说明', flow: 'result' },
  out_of_scope: { key: 'result', label: '人工接续', hint: '当前产品需要人工协助', flow: 'result' },
};

/** Only the active issue's case can describe its progress. */
export function caseStatusOf(timeline: TimelineItem[] = [], activeIssueId?: string | null): string | null {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const item = timeline[i]!;
    if (item.kind === 'case_changed' && (activeIssueId ? item.issue_id === activeIssueId : !item.issue_id)) return item.status;
  }
  return null;
}

/** A route is a roadmap, not evidence that every earlier step was completed. */
export function progressFor(stage: Stage | null, caseStatus?: string | null) {
  if (!stage || !STAGES[stage]) return { steps: DIAGNOSIS, active: -1, label: null };
  let current: Step = STAGES[stage];
  const service = STAGES[stage].flow === 'service' || (!!caseStatus && (stage === 'done' || stage === 'intake'));
  let steps = service ? SERVICE : STAGES[stage].flow === 'query' ? QUERY : STAGES[stage].flow === 'result' ? [current] : DIAGNOSIS;
  if (service && caseStatus && ['execute', 'track', 'awaiting_human', 'done'].includes(stage)) {
    const key = ['closed', 'closed_unresolved', 'tracking', 'escalated_summary'].includes(caseStatus) ? 'tracking' : 'execution';
    current = { key, label: CASE_LABELS[caseStatus] ?? current.label, hint: caseStatus === 'executing_failed' ? '可重试原申请，进度以回执为准' : caseStatus === 'closed' ? '案件已结案，仍可查看历史记录' : current.hint };
  }
  steps = steps.map(step => step.key === current.key ? current : step);
  return { steps, active: steps.findIndex(step => step.key === current.key), label: current.label };
}
