/** 节点瀑布：一次 run 里每个节点一条横条，长度 = 耗时，位置 = 先后。
 *  下面挂着该节点上发生的模型调用与检索，用来回答「这一步慢在哪」。 */
import { ms, nodeLabel } from '../format';
import type { ModelCall, NodeRun, RetrievalCall } from '../types';

export function RunWaterfall({ nodes, models, retrievals, selected, onSelect }: {
  nodes: NodeRun[];
  models: ModelCall[];
  retrievals: RetrievalCall[];
  selected: number | null;
  onSelect: (idx: number) => void;
}) {
  if (!nodes.length) {
    return <p className="empty">这次运行没有节点轨迹（会话早于观测台上线，或 checkpoint 已过保留期）</p>;
  }
  const known = nodes.filter((n) => n.duration_ms !== null);
  const total = known.reduce((acc, n) => acc + (n.duration_ms ?? 0), 0);
  // 没有耗时（回填的历史数据）时退化为等宽，只表达顺序
  const scale = total > 0 ? total : nodes.length;
  let cursor = 0;

  return (
    <div className="waterfall">
      {nodes.map((node) => {
        const duration = node.duration_ms ?? scale / nodes.length;
        const left = (cursor / scale) * 100;
        const width = Math.max((duration / scale) * 100, 1.5);
        cursor += duration;
        const nodeModels = models.filter((m) => m.node === node.node);
        const nodeRetrievals = retrievals.filter((r) => r.node === node.node);
        return (
          <div key={`${node.run_id}-${node.idx}`}>
            <div className="wf-row" aria-selected={selected === node.idx} role="button" tabIndex={0}
              onClick={() => onSelect(node.idx)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(node.idx); } }}>
              <span className="name">
                {node.idx}. {nodeLabel(node.node)}
                {node.status !== 'ok' && <span className="sub">{node.status === 'interrupt' ? '在此等待用户' : '出错'}</span>}
              </span>
              <span className="track">
                <span className="fill" style={{ left: `${left}%`, width: `${width}%` }} />
              </span>
              <span className="n muted">{ms(node.duration_ms)}</span>
            </div>
            {nodeModels.map((m) => (
              <div className="wf-child" key={`m-${m.task}-${m.created_at}`}>
                模型 {m.task} · {m.model_used ?? '—'} · {ms(m.latency_ms)}
                {m.fallback_used && ' · 已降级'}
                {m.status !== 'ok' && ` · ${m.status}`}
              </div>
            ))}
            {nodeRetrievals.map((r) => (
              <div className="wf-child" key={`r-${r.kb}-${r.created_at}`}>
                检索 {r.kb} · 第 {r.round} 轮 · {r.status === 'ok' ? `命中 ${r.hits}` : r.status} · {ms(r.latency_ms)}
              </div>
            ))}
          </div>
        );
      })}
      <p className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
        {total > 0 ? `节点合计 ${ms(total)}` : '历史回填数据没有节点耗时，条形仅表示顺序'}
      </p>
    </div>
  );
}
