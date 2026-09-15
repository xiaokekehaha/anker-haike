/** 经营面板：先给 KPI，再给趋势与构成，最后是模型 / 检索健康与聚合流程图。 */
import { useMemo, useState } from 'react';
import { api } from '../api';
import { l3Api } from '../l3';
import { BarList, Kpi, OutcomeStack, TrendChart } from '../components/Charts';
import { GraphView } from '../components/GraphView';
import { count, defaultWindow, ms, percent, reasonText } from '../format';
import { useAsync } from '../useAsync';

const DIMS = [
  { key: 'category', label: '品类' },
  { key: 'sku', label: '型号' },
  { key: 'plan', label: '排障计划' },
  { key: 'reason', label: '结局原因' },
  { key: 'emotion', label: '情绪' },
] as const;

const RANGES = [
  { days: 1, label: '今天' },
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 365, label: '全部' },
];

export function Dashboard() {
  const [days, setDays] = useState(7);
  const [dim, setDim] = useState<string>('category');
  // 必须记忆：直接在渲染里算 Date.now() 会让每次渲染都得到新的 from，
  // 进而无限触发重新取数（实测把请求打成了死循环）。
  const from = useMemo(() => defaultWindow(days).from, [days]);
  const bucket = days <= 1 ? 'hour' : 'day';

  const overview = useAsync(() => api.overview({ from, bucket, dim }), [from, bucket, dim]);
  const l3 = useAsync(() => l3Api.metrics(from), [from]);
  const flow = useAsync(() => api.flow({ from }), [from]);
  const topology = useAsync(() => api.topology(), []);

  if (overview.error) return <p className="empty">读取失败：{overview.error}</p>;
  const data = overview.data;
  const totals = data?.totals ?? {};
  const latency = data?.latency ?? {};

  return (
    <>
      <div className="filters">
        {RANGES.map((r) => (
          <button key={r.days} className="btn" data-variant={days === r.days ? 'primary' : undefined}
            onClick={() => setDays(r.days)}>{r.label}</button>
        ))}
        <span className="muted" style={{ fontSize: 12 }}>
          {overview.loading ? '加载中…' : `共 ${count(totals.sessions)} 个会话`}
        </span>
      </div>

      {l3.error && <p className="empty">L3 指标读取失败：{l3.error}</p>}
      <div className="grid kpis" style={{ marginBottom: 16 }}>
        <Kpi label="独立托管率" value={percent(l3.data?.managed_rate)} hint="按问题计数：独立解决、独立闭环、咨询回答 ÷ 所有终态及转人工、放弃；剔除 replay / smoke。申请提交仍在跟踪，不算闭环。" note={`完成 ${count(l3.data?.managed)} / 终态 ${count(l3.data?.terminal)}`} />
        <Kpi label="意图准确率" value={percent(l3.data?.intent_accuracy)} hint="人工标注意图正确的问题数 ÷ 已标注意图的问题数；无标注时暂无数据。" note={`已标注 ${count(l3.data?.intent_labeled)}`} />
        <Kpi label="净满意度 NSS" value={percent(l3.data?.nss)} hint="4–5 分占比减去 1–2 分占比；3 分中性。评分不改变案件状态。" note={`评分覆盖率 ${percent(l3.data?.rating_coverage)}`} />
        <Kpi label="越权执行次数" value={l3.data?.unauthorized_executions == null ? '—' : count(l3.data.unauthorized_executions)} hint="写动作成功但缺少四项完整授权检查，或任一检查失败的执行次数。" />
      </div>
      <div className="grid kpis" style={{ marginBottom: 16 }}>
        <Kpi label="自助解决率" value={percent(data?.rates.self_service)}
          hint="已解决 ÷（已解决 + 系统原因转人工 + 排障中途放弃）；用户主动要人工、安全升级、范围外不计入"
          note={`已解决 ${count(totals.resolved)} 个`} />
        <Kpi label="闭环率" value={percent(data?.rates.closure)}
          hint="已解决 ÷（已解决 + 需人工处理）：有明确结局的会话里解决掉的比例"
          note={`需人工处理 ${count(totals.escalated)} 个`} />
        <Kpi label="首次可见 P95" value={ms(latency.first_visible_p95)}
          hint="从收到消息到第一段可见文字" note={`中位 ${ms(latency.first_visible_p50)}`} />
        <Kpi label="首张卡片 P95" value={ms(latency.card_ready_p95)}
          hint="从收到消息到第一张卡片" note={`中位 ${ms(latency.card_ready_p50)}`} />
        <Kpi label="模型调用" value={count(totals.model_calls)}
          note={`${count(totals.tokens_in)} + ${count(totals.tokens_out)} tok`} />
      </div>

      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>会话趋势</h2>
          <p className="sub">每{bucket === 'hour' ? '小时' : '天'}的会话量与其中已解决的数量。</p>
          <TrendChart
            labels={(data?.series ?? []).map((s) => s.at)}
            series={[
              { key: 'sessions', label: '会话数', color: 'var(--viz-series-1)', values: (data?.series ?? []).map((s) => s.sessions) },
              { key: 'resolved', label: '已解决', color: 'var(--viz-series-2)', values: (data?.series ?? []).map((s) => s.resolved) },
            ]}
          />
        </div>
        <div className="card">
          <h2>结局构成</h2>
          <p className="sub">「被打断」与「已过期」不计入解决率，因为结局本身不可知。</p>
          <OutcomeStack totals={totals} />
        </div>
      </div>

      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>分布</h2>
          <p className="sub">按维度看会话都落在哪里。</p>
          <div className="filters">
            {DIMS.map((d) => (
              <button key={d.key} className="chip" aria-pressed={dim === d.key} onClick={() => setDim(d.key)}>
                {d.label}
              </button>
            ))}
          </div>
          <BarList rows={(data?.breakdown ?? []).slice(0, 10).map((b) => ({
            value: dim === 'reason' ? reasonText(b.value) : b.value, sessions: b.sessions,
          }))} />
        </div>
        <div className="card">
          <h2>模型与检索</h2>
          <p className="sub">按任务看调用量、降级与 P95 耗时。</p>
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr><th>任务</th><th>模型</th><th className="num">调用</th><th className="num">降级</th><th className="num">出错</th><th className="num">P95</th></tr>
              </thead>
              <tbody>
                {(data?.models ?? []).slice(0, 8).map((m) => (
                  <tr key={`${m.task}-${m.model_used}`}>
                    <td>{m.task}</td>
                    <td className="mono">{m.model_used ?? '—'}</td>
                    <td className="num">{m.calls}</td>
                    <td className="num">{m.fallbacks || '—'}</td>
                    <td className="num">{m.errors || '—'}</td>
                    <td className="num">{ms(m.p95_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(data?.retrieval ?? []).length > 0 && (
            <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
              检索：{data!.retrieval.map((r) => `${r.kb} ${r.status} ${r.n}`).join(' · ')}
            </p>
          )}
        </div>
      </div>

      <div className="card">
        <h2>整体流程</h2>
        <p className="sub">边越粗走的人越多，节点颜色越深经过越多。点节点看名称，滚轮缩放。</p>
        {topology.data
          ? <GraphView topology={topology.data} traffic={flow.data} />
          : <p className="empty">{topology.error ?? '加载流程图…'}</p>}
      </div>
    </>
  );
}
