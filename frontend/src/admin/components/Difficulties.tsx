/** 五难点证据：从会话快照、会话事实与 run 轨迹里派生「看图 / 问清 / 分流 / 接稳 / 幻觉」各自的处理证据。
 *  只陈述发生了什么，不打分；评审看的是「有没有做、做到哪一步」。 */
import type { SessionState } from '../../state/types';
import type { TimelineItem } from '../../types/snapshot';
import type { ServiceCase } from '../l3';
import { EMOTION_TEXT, GATE_TEXT, STRATEGY_TEXT, nodeLabel, reasonText } from '../format';
import type { RunFacts, SessionRow } from '../types';

type Item = { label: string; value: string; tone?: 'ok' | 'warn' | 'muted' };
type Section = { key: string; title: string; question: string; items: Item[] };

function items<T extends TimelineItem['kind']>(timeline: TimelineItem[], kind: T): Extract<TimelineItem, { kind: T }>[] {
  return timeline.filter((t): t is Extract<TimelineItem, { kind: T }> => t.kind === kind);
}

export function deriveDifficulties(state: SessionState | null, session: (SessionRow & Record<string, unknown>) | null, runs: RunFacts[], serviceCase: ServiceCase | null): Section[] {
  const tl = state?.timeline ?? [];
  const steps = items(tl, 'step_card');
  const summaries = items(tl, 'escalation_summary');
  const summary = summaries[summaries.length - 1]?.summary ?? null;
  const userImages = items(tl, 'user_message').reduce((acc, m) => acc + (m.images?.length ?? m.image_ids?.length ?? 0), 0);
  const retakes = items(tl, 'retake_card');
  const seen = steps.filter((s) => s.seen).length;
  // 白名单键即使没触发读图也会以 null 落库，只算有值的
  const visionNodes = runs.flatMap((r) => r.nodes.filter((n) => n.summary?.vision_status));
  const evidenceGroups = items(tl, 'evidence');
  const stepsWithEvidence = steps.filter((s) => (s.step.evidence_ids?.length ?? 0) > 0).length;
  const tools = items(tl, 'tool');
  const failedTools = tools.filter((t) => t.status === 'failed').length;
  const modelCalls = runs.flatMap((r) => (Array.isArray(r.model_calls) ? r.model_calls : []));
  const fallbacks = modelCalls.filter((m) => m.fallback_used).length;
  const clarifications = Number(session?.clarifications ?? 0);
  const issues = state?.issues.length ?? 0;
  const taskQueue = (summary?.task_queue ?? []).length;
  const emotionLevel = summary?.emotion.level ?? session?.emotion_level ?? null;
  const strategy = summary?.emotion.strategy ?? null;
  const track = (summary?.emotion_track ?? []) as { level?: string }[];
  const gate = serviceCase?.gate_result ?? summary?.gate_result ?? null;

  return [
    {
      key: 'vision', title: '看图', question: '图片有没有被读懂并用到排障里',
      items: [
        { label: '用户上传图片', value: `${userImages} 张`, tone: userImages ? 'ok' : 'muted' },
        { label: '读图结果写进步骤卡', value: `${seen} 步带「我们看到的」`, tone: seen ? 'ok' : 'muted' },
        { label: '补拍请求', value: retakes.length ? `${retakes.length} 次${retakes.some((r) => r.skipped) ? '（有跳过）' : ''}` : '无', tone: 'muted' },
        { label: '读图节点', value: visionNodes.length ? visionNodes.map((n) => `${nodeLabel(n.node)} ${String(n.summary?.vision_status)}`).join('；') : '本会话未触发', tone: 'muted' },
      ],
    },
    {
      key: 'ask', title: '问清', question: '口语描述有没有被追问成可判定的现象',
      items: [
        { label: '澄清轮次', value: `${clarifications} 次${session?.outcome_reason === 'R7' ? '（超限转人工）' : ''}`, tone: session?.outcome_reason === 'R7' ? 'warn' : 'muted' },
        { label: '排障步骤', value: `${steps.length} 步，${steps.filter((s) => s.feedback).length} 步有反馈`, tone: 'muted' },
      ],
    },
    {
      key: 'route', title: '分流', question: '多个诉求与不同处置路径有没有被分开',
      items: [
        { label: '会话内问题数', value: `${issues || 1} 个`, tone: 'muted' },
        { label: '待接续诉求', value: taskQueue ? `${taskQueue} 项` : '无', tone: 'muted' },
        { label: '结局原因', value: session ? `${session.outcome_reason ?? '—'} · ${reasonText(session.outcome_reason)}` : '—', tone: 'muted' },
        { label: '服务案件', value: serviceCase ? `${serviceCase.status}${serviceCase.warranty ? ` · 质保 ${serviceCase.warranty.status}` : ''}` : '未进入办理', tone: 'muted' },
      ],
    },
    {
      key: 'emotion', title: '接稳', question: '情绪有没有被分级并换策略',
      items: [
        { label: '情绪等级', value: emotionLevel ? EMOTION_TEXT[emotionLevel] ?? emotionLevel : '未判断', tone: emotionLevel && emotionLevel !== 'calm' ? 'warn' : 'muted' },
        { label: '应对策略', value: strategy ? STRATEGY_TEXT[strategy] ?? strategy : '—', tone: 'muted' },
        { label: '情绪轨迹', value: track.length ? track.map((t) => EMOTION_TEXT[String(t.level)] ?? String(t.level)).join(' → ') : '升级前不记录逐轮情绪（契约待扩）', tone: 'muted' },
        { label: '投诉风险', value: serviceCase?.complaint_risk ? '已标记，案件优先' : '无', tone: serviceCase?.complaint_risk ? 'warn' : 'muted' },
      ],
    },
    {
      key: 'grounding', title: '幻觉', question: '每一步有没有依据，办理有没有过授权门',
      items: [
        { label: '步骤带依据', value: steps.length ? `${stepsWithEvidence} / ${steps.length} 步` : '无步骤', tone: steps.length && stepsWithEvidence === steps.length ? 'ok' : steps.length ? 'warn' : 'muted' },
        { label: '检索', value: `${tools.length} 次${failedTools ? `，失败 ${failedTools}` : ''}；${evidenceGroups.reduce((acc, g) => acc + g.items.length, 0)} 条片段`, tone: failedTools ? 'warn' : 'muted' },
        { label: '模型降级', value: fallbacks ? `${fallbacks} 次` : '无', tone: fallbacks ? 'warn' : 'muted' },
        { label: '授权门', value: gate ? gate.checks.map((c) => `${c.passed ? '✓' : '×'} ${GATE_TEXT[c.name] ?? c.name}`).join(' · ') : '未进入办理', tone: gate ? (gate.passed ? 'ok' : 'warn') : 'muted' },
      ],
    },
  ];
}

export function Difficulties({ sections }: { sections: Section[] }) {
  return (
    <div className="diff">
      {sections.map((s) => (
        <section key={s.key} className="diff-section">
          <h3>{s.title}<span>{s.question}</span></h3>
          <dl>
            {s.items.map((it) => (
              <div key={it.label}><dt>{it.label}</dt><dd data-tone={it.tone ?? 'muted'}>{it.value}</dd></div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
