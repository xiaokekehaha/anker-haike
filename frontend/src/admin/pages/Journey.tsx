/** 会话旅程：左选 run，中间四视图（对话 / 五难点 / 节点瀑布 / 流程图），右栏按视图切换服务记录或节点详情。 */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CASE_LABELS } from '../../state/progress';
import { api } from '../api';
import { l3Api } from '../l3';
import { Badge } from '../components/Charts';
import { Difficulties, deriveDifficulties } from '../components/Difficulties';
import { GraphView } from '../components/GraphView';
import { NodeDetail } from '../components/NodeDetail';
import { RunWaterfall } from '../components/RunWaterfall';
import { LabelDialog } from '../components/LabelDialog';
import { SessionRecord, SessionView, useSnapshotState } from '../components/SessionView';
import { EMOTION_TEXT, ms, nodeLabel, reasonText, when } from '../format';
import { useAsync } from '../useAsync';
import type { ModelCall, NodeRun, RetrievalCall } from '../types';

type View = 'chat' | 'difficulties' | 'waterfall' | 'graph';

export function Journey() {
  const { id = '' } = useParams();
  const journey = useAsync(() => api.journey(id), [id]);
  const topology = useAsync(() => api.topology(), []);
  const cases = useAsync(() => l3Api.queue(''), []);
  const [runIdx, setRunIdx] = useState(0);
  const [view, setView] = useState<View>('chat');
  const [nodeIdx, setNodeIdx] = useState<number | null>(null);
  const [labeling, setLabeling] = useState(false);
  const [hover, setHover] = useState<string[]>([]);

  const runs = journey.data?.runs ?? [];
  const run = runs[Math.min(runIdx, Math.max(runs.length - 1, 0))];
  const nodes: NodeRun[] = run?.nodes ?? [];
  const models: ModelCall[] = Array.isArray(run?.model_calls) ? run!.model_calls : [];
  const retrievals: RetrievalCall[] = run?.retrieval_calls ?? [];
  const path = useMemo(() => nodes.map((n) => n.node), [nodes]);
  const selected = nodes.find((n) => n.idx === nodeIdx) ?? null;
  const state = useSnapshotState(journey.data?.snapshot);
  const serviceCase = useMemo(() => (cases.data?.items ?? []).find((c) => c.session_id === id) ?? null, [cases.data, id]);
  const difficulties = useMemo(() => deriveDifficulties(state, journey.data?.session ?? null, runs, serviceCase), [state, journey.data, runs, serviceCase]);

  if (journey.error) return <p className="empty">读取失败：{journey.error} <Link className="link" to="/sessions">返回列表</Link></p>;
  if (!journey.data) return <p className="empty">加载中…</p>;
  const session = journey.data.session;
  const showRecord = view === 'chat' || view === 'difficulties';

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <h2 style={{ fontSize: 15 }}>{session.first_question || '（无文本）'}</h2>
            <p className="sub mono">{id}</p>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12.5 }}>
              <Badge outcome={session.outcome} />
              <span className="muted">原因 {reasonText(session.outcome_reason)}</span>
              <span className="muted">产品 {session.sku ?? session.category ?? '未识别'}</span>
              {session.emotion_level && <span className="muted">情绪 {EMOTION_TEXT[session.emotion_level] ?? session.emotion_level}</span>}
              <span className="muted">{session.runs} 轮 · {session.steps_executed} 个步骤</span>
              <span className="muted">{when(session.last_run_at)}</span>
              {serviceCase && <Link className="link" to={`/desk/${serviceCase.case_id}`}>案件 · {CASE_LABELS[serviceCase.status] ?? serviceCase.status}</Link>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" data-variant="primary" onClick={() => setLabeling(true)}>{journey.data.case ? '改复盘标注' : '标注这个会话'}</button>
            <Link className="btn" to="/sessions" style={{ textDecoration: 'none' }}>返回列表</Link>
          </div>
        </div>
        {journey.data.case && (
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            已复盘 {journey.data.case.verdict} · {journey.data.case.reason_tags.join('、') || '无标签'}{journey.data.case.note && ` · ${journey.data.case.note}`}
          </p>
        )}
      </div>

      <div className="journey">
        <div className="runlist">
          {runs.map((r, i) => (
            <button key={r.run_id} aria-pressed={i === runIdx} onClick={() => { setRunIdx(i); setNodeIdx(null); }}>
              第 {r.seq_no} 轮 · {entryText(r.entry)}
              <span className="meta">{ms(r.duration_ms)} · {r.node_count} 节点<br />{doneText(r.done_reason)}</span>
            </button>
          ))}
          {runs.length === 0 && <p className="muted" style={{ fontSize: 12 }}>没有运行记录。</p>}
        </div>

        <div className="card">
          <div className="tabs">
            <button aria-pressed={view === 'chat'} onClick={() => setView('chat')}>对话</button>
            <button aria-pressed={view === 'difficulties'} onClick={() => setView('difficulties')}>五难点证据</button>
            <button aria-pressed={view === 'waterfall'} onClick={() => setView('waterfall')}>节点瀑布</button>
            <button aria-pressed={view === 'graph'} onClick={() => setView('graph')}>流程图</button>
          </div>
          {view === 'chat' && <SessionView snapshot={journey.data.snapshot} onHover={setHover} />}
          {view === 'difficulties' && <Difficulties sections={difficulties} />}
          {view === 'waterfall' && <RunWaterfall nodes={nodes} models={models} retrievals={retrievals} selected={nodeIdx} onSelect={setNodeIdx} />}
          {view === 'graph' && (topology.data ? (
            <>
              <p className="sub">高亮的是这一轮实际走过的节点，序号即先后。</p>
              <GraphView topology={topology.data} path={path} selected={selected?.node ?? null} small onSelect={(node) => setNodeIdx(nodes.find((n) => n.node === node)?.idx ?? null)} />
              <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>路径：{path.map(nodeLabel).join(' → ') || '（无节点轨迹）'}</p>
            </>
          ) : <p className="empty">加载流程图…</p>)}
        </div>

        {showRecord ? (
          <div className="card detail"><h2>服务记录</h2><p className="sub">客户端右栏同款。</p><SessionRecord snapshot={journey.data.snapshot} highlight={hover} /></div>
        ) : (
          <NodeDetail node={selected} models={models} retrievals={retrievals} />
        )}
      </div>

      {labeling && (
        <LabelDialog sessionId={id} current={journey.data.case} onClose={() => setLabeling(false)} onSaved={() => { setLabeling(false); journey.reload(); }} />
      )}
    </>
  );
}

function entryText(entry: string | null): string {
  if (!entry) return '—';
  if (entry === 'message') return '用户发消息';
  if (entry === 'action:retry') return '重试';
  const kind = entry.replace('action:', '');
  return { select_product: '选择产品', step_feedback: '步骤反馈', confirm_receipt: '确认凭证', skip_receipt: '跳过凭证', request_human: '要求人工', rediagnose: '补充信息', resumed: '回应卡片' }[kind] ?? entry;
}

function doneText(reason: string | null): string {
  return { completed: '已完成', awaiting_input: '等用户回应', error: '出错', cancelled: '已取消' }[reason ?? ''] ?? reason ?? '—';
}
