/** 右栏：选中节点的判定字段、模型调用与检索明细。 */
import { ms, nodeLabel, reasonText } from '../format';
import type { ModelCall, NodeRun, RetrievalCall } from '../types';
import { ContextMetrics } from './ContextMetrics';

const SUMMARY_TEXT: Record<string, string> = {
  product_state: '产品状态', category: '品类', knowledge_status: '知识检索',
  vision_status: '读图', escalate_reason: '升级原因', stage: '阶段', substage: '子阶段',
  out_of_scope: '范围外', rewrite_used: '用过改写', retrieval_rounds: '检索轮次',
  decision: '消歧判定', verify: '反馈判定', rule: '命中规则', diagnose_outcome: '诊断结论',
  plan_id: '排障计划', receipt_status: '凭证状态', backfilled: '历史回填',
  relaxed_level: '候选选择', candidate_rejection_counts: '各级候选排除记录',
};

const VALUE_TEXT: Record<string, string> = {
  ok: '有命中', no_match: '无命中', unavailable: '不可用', replay: '回放',
  confirmed_sku: '已确认型号', category_only: '只知品类', unknown: '未知',
  continue: '继续', clarify: '澄清', escalate: '升级', next: '下一步', done: '完成',
  evidence: '有依据', standard_flow: '走标准流程', skipped: '跳过', no_vision: '无读图',
  failed: '失败', true: '是', false: '否',
  strict: '常规候选', observation: '依据观察重选',
};

const REJECTION_TEXT: Record<string, string> = {
  plan_missing: '计划不存在', plan_model_mismatch: '型号不适用', plan_exhausted: '计划已耗尽',
  confidence_below_threshold: '模型置信度不足', diagnostic_plan_constraint: '旧问诊限制',
  excluded_by_observation: '观察不匹配', observation_missing: '等待观察结果',
  observation_requires_execution: '需先完成检查', already_executed: '步骤已执行',
  duplicate_instruction_src: '同一操作已执行', user_paused: '用户暂停',
  resource_unavailable: '操作资源缺失', step_blocked: '步骤仍有阻碍',
};

function rejectionsText(value: unknown): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '无';
  return Object.entries(value)
    .filter(([reason, count]) => Object.hasOwn(REJECTION_TEXT, reason) && typeof count === 'number' && count > 0)
    .map(([reason, count]) => `${REJECTION_TEXT[reason]} ${count} 次`).join('；') || '无';
}

function show(value: unknown): string {
  const text = String(value);
  return VALUE_TEXT[text] ?? reasonText(text) ?? text;
}

export function NodeDetail({ node, models, retrievals }: {
  node: NodeRun | null;
  models: ModelCall[];
  retrievals: RetrievalCall[];
}) {
  if (!node) {
    return (
      <div className="card detail">
        <h2>节点详情</h2>
        <p className="sub">在中间的瀑布或流程图里点一个节点。</p>
      </div>
    );
  }
  const nodeModels = models.filter((m) => m.node === node.node);
  const nodeRetrievals = retrievals.filter((r) => r.node === node.node);
  const summary = Object.entries(node.summary ?? {}).filter(([key]) => key !== 'context_metrics');
  const contextMetrics = node.summary?.context_metrics;
  return (
    <div className="card detail">
      <h2>{node.idx}. {nodeLabel(node.node)}</h2>
      <p className="sub mono">{node.node} · {ms(node.duration_ms)}{node.status !== 'ok' && ` · ${node.status}`}</p>
      <ContextMetrics value={contextMetrics} />
      {summary.length > 0 && (
        <dl>
          {summary.map(([key, value]) => (
            <div key={key}>
              <dt>{SUMMARY_TEXT[key] ?? key}</dt>
              <dd>{key === 'candidate_rejection_counts' ? rejectionsText(value) : show(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {nodeModels.length > 0 && (
        <>
          <dt style={{ marginTop: 14 }}>模型调用</dt>
          {nodeModels.map((m) => (
            <dd key={`${m.task}-${m.created_at}`} className="mono">
              {m.task} · {m.model_used ?? '—'} · {ms(m.latency_ms)} · {m.tokens_in ?? 0}/{m.tokens_out ?? 0} tok
              {m.attempts > 1 && ` · ${m.attempts} 次尝试`}
              {m.fallback_used && ' · 已降级'}
              {m.error_type && ` · ${m.error_type}`}
            </dd>
          ))}
        </>
      )}
      {nodeRetrievals.length > 0 && (
        <>
          <dt style={{ marginTop: 14 }}>检索</dt>
          {nodeRetrievals.map((r) => (
            <dd key={`${r.kb}-${r.created_at}`} className="mono">
              {r.kb} · 第 {r.round} 轮 · {show(r.status)} · 命中 {r.hits ?? 0}/{r.allowed_count ?? 0}
              {r.top_score !== null && ` · 最高分 ${r.top_score.toFixed(4)}`}
              {r.query && <div className="muted">{r.query}</div>}
            </dd>
          ))}
        </>
      )}
      {summary.length === 0 && !contextMetrics && nodeModels.length === 0 && nodeRetrievals.length === 0 && (
        <p className="muted" style={{ fontSize: 12.5 }}>这个节点没有留下额外判定信息。</p>
      )}
    </div>
  );
}
