/** 展示层的口径与文案：结局、时长、比率。中文标签集中在这里，图表与表格共用。 */
import type { Outcome } from './types';

/** 结局 → 中文 + 状态角色。角色决定颜色槽（viz-good / warning / critical / serious / neutral），
 *  但颜色永远不单独承载含义：每处都带文字标签（dataviz 技能的 icon+label 要求）。 */
export const OUTCOME: Record<Outcome, { label: string; role: Role; hint: string }> = {
  resolved: { label: '已解决', role: 'good', hint: '给出结束语，用户确认解决' },
  escalated: { label: '需人工处理', role: 'warning', hint: '问题摘要已整理；是否接单以实际人工状态为准' },
  abandoned: { label: '已放弃', role: 'serious', hint: '等用户回应但长时间没有下文' },
  errored: { label: '出错', role: 'critical', hint: '节点异常或超时' },
  awaiting_user: { label: '等用户', role: 'neutral', hint: '正等卡片反馈' },
  clarifying: { label: '澄清中', role: 'neutral', hint: '已发出追问' },
  in_progress: { label: '进行中', role: 'neutral', hint: '尚未收尾' },
  interrupted: { label: '被打断', role: 'neutral', hint: '服务重启中断，成败未知，不计入解决率' },
  unknown: { label: '已过期', role: 'neutral', hint: '会话数据已按保留期清理，结局不可知' },
};

export type Role = 'good' | 'warning' | 'critical' | 'serious' | 'neutral';

/** 堆叠顺序：good → warning → critical → serious → neutral。
 *  这个相邻顺序通过了 dataviz 的 CVD 与常视觉分辨检查（warning 与 serious 不相邻）。 */
export const STACK_ORDER: Outcome[] = [
  'resolved', 'escalated', 'errored', 'abandoned',
  'awaiting_user', 'clarifying', 'in_progress', 'interrupted', 'unknown',
];

export function outcomeLabel(outcome: string): string {
  return OUTCOME[outcome as Outcome]?.label ?? outcome;
}

export function outcomeRole(outcome: string): Role {
  return OUTCOME[outcome as Outcome]?.role ?? 'neutral';
}

/** 升级原因（规则号）→ 人话。R3/R4/R8 属政策，不计入「系统没解决」。 */
export const REASON_TEXT: Record<string, string> = {
  R1: '步骤走完仍未解决', R1b: '步骤走完仍未解决', R1c: '步骤走完仍未解决',
  R2: '适用步骤已耗尽', R3: '用户要求人工', R4: '安全风险',
  R5: '没有适用排查方案', R7: '继续处理所需信息待确认', R8: '不在支持范围',
  solved: '用户确认解决', plan_done: '计划执行完毕',
  server_restarted: '服务重启打断', node_failed: '节点异常',
  deadline_exceeded: '超过时限', no_checkpoint: '数据已过保留期',
  step_feedback: '等步骤反馈', select_product: '等选择产品',
  upload_receipt: '等上传凭证', confirm_receipt: '等确认凭证',
};

export function reasonText(reason: string | null): string {
  if (!reason) return '—';
  return REASON_TEXT[reason] ?? reason;
}

/** 复盘原因标签 → 中文。键与后端 derive.REASON_TAGS 一致。 */
export const TAG_TEXT: Record<string, string> = {
  intent_correct: '意图正确', intent_wrong: '意图有误',
  knowledge_missing: '知识缺失', retrieval_mismatch: '检索错配', wrong_plan: '计划不对',
  bad_step_wording: '步骤话术差', model_quality: '模型输出差', model_fallback: '降级导致',
  rule_false_positive: '规则误触', product_unrecognized: '产品未识别',
  emotion_mishandled: '情绪处理不当', latency: '太慢', ui_flow: '交互问题',
  user_abandoned: '用户中途离开', exemplary: '值得沉淀',
};

export const VERDICT_TEXT: Record<string, string> = { good: '好案例', bad: '坏案例', review: '待复盘' };
export const CASE_STATUS_TEXT: Record<string, string> = {
  open: '待处理', exported: '已导出', fixed: '已修复', wontfix: '不修',
};

/** 节点名 → 中文（与图节点一一对应）。 */
export const NODE_TEXT: Record<string, string> = {
  understand: '理解诉求', dialogue: '对话回应', commit_issue: '保存问题',
  service_context: '核实服务信息', propose: '计算方案', authorize: '检查授权', execute: '办理业务', track: '跟踪服务单', await_human: '等待人工审核', consult: '业务查询', apply_human_decision: '应用审核决定', advance_tasks: '接续下一需求', prepare_retake: '请求补拍', vision_conflict: '核实图文差异',
  __start__: '开始', __end__: '结束', intake: '理解诉求', rediagnose: '补充信息',
  reassure: '安抚', disambiguate: '产品消歧', prepare_card: '准备产品卡', clarify: '澄清追问',
  vision: '读图', retrieve: '检索知识', reply: '生成回复', guide: '下发步骤',
  await_input: '等待用户', apply_action: '处理动作', escalate: '升级', summarize: '生成摘要',
  prepare_receipt: '索取凭证', receipt_extract: '识别凭证', human_request: '转人工',
  out_of_scope: '范围外', close: '收尾',
};

export const STAGE_TEXT: Record<string, string> = {
  start: '入口', intake: '理解', disambiguate: '消歧', diagnose: '诊断', guide: '排障',
  wait: '等待', escalate: '升级', out_of_scope: '范围外', done: '完成', end: '结束',
};

export function nodeLabel(node: string): string {
  return NODE_TEXT[node] ?? node;
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
}

export function percent(value: number | null | undefined): string {
  // 分母为 0 时后端返回 null——「没有数据」不能显示成 0%
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value >= 10000 ? `${(value / 1000).toFixed(1)}k` : String(value);
}

export function when(iso: string | null | undefined): string {
  if (!iso) return '—';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '—';
  const diff = Date.now() - at.getTime();
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return at.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function dayLabel(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}

/** 默认时间窗：近 7 天。 */
export function defaultWindow(days = 7): { from: string } {
  return { from: new Date(Date.now() - days * 86_400_000).toISOString() };
}

/** 等待时长分级：< 1 h 新鲜、< 1 d 需关注、≥ 1 d 逾期。颜色永远配文字。 */
export function sla(iso: string): { label: string; level: 'fresh' | 'aging' | 'late' } {
  const diff = Math.max(0, Date.now() - Date.parse(iso));
  if (Number.isNaN(diff)) return { label: '—', level: 'fresh' };
  if (diff < 3_600_000) return { label: `${Math.max(1, Math.round(diff / 60_000))} 分钟`, level: 'fresh' };
  if (diff < 86_400_000) return { label: `${Math.round(diff / 3_600_000)} 小时`, level: 'aging' };
  return { label: `${Math.round(diff / 86_400_000)} 天`, level: 'late' };
}

/** 服务单类型（主办方 SOP：提交后一律转人工） */
export const SERVICE_TYPE_TEXT: Record<string, string> = {
  replace: '换货单', refund: '退款单', reship: '补发单', carrier_investigation: '承运商调查单',
};
/** 订单质保判断 */
export const WARRANTY_TEXT: Record<string, string> = {
  in_warranty: '保内', out_of_warranty: '已过保', unauthorized_dealer: '非授权经销商', unknown: '待核实',
};
export const WARRANTY_BASIS_TEXT: Record<string, string> = { order: '订单质保结束日期', dealer: '授权经销商购买日起 12 个月', none: '无依据' };
export const EMOTION_TEXT: Record<string, string> = { calm: '平静', anxious: '焦急', dissatisfied: '不满', angry: '愤怒', complaint_risk: '投诉风险' };
export const STRATEGY_TEXT: Record<string, string> = {
  normal: '常规处理', reassure_first: '先安抚再排查', reassure_and_shorten: '先安抚、缩短步骤', direct_resolution: '直接给方案', de_escalate_and_offer_human: '降温并提供人工',
};
/** 服务单提交闸门四项检查 */
export const GATE_TEXT: Record<string, string> = { eligibility: '办理资格', evidence: 'SOP 证据与客户确认', safety: '安全限制', idempotency: '幂等键' };

/** L3 案件状态分组（工作台 tab） */
export const CASE_GROUPS: { key: string; label: string; statuses: string[] }[] = [
  { key: 'awaiting', label: '待审批', statuses: ['awaiting_approval'] },
  { key: 'working', label: '办理中', statuses: ['open', 'diagnosing', 'proposing', 'awaiting_confirmation', 'approved', 'rejected', 'executing', 'executing_failed', 'reopened'] },
  { key: 'tracking', label: '跟踪中', statuses: ['tracking'] },
  { key: 'closed', label: '已结束', statuses: ['closed', 'closed_unresolved', 'escalated_summary'] },
];

export function showValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value);
  const text = String(value);
  return SERVICE_TYPE_TEXT[text] ?? WARRANTY_TEXT[text] ?? text;
}
