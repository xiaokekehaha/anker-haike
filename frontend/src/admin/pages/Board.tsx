/** 运营看板：一屏一个分母。第一行业务指标按「问题」计；第二行五个评审难点；第三行体验与性能按会话 / run 计；
 *  下面是趋势、结局构成、分布。聚合流程图与模型表搬到「诊断」。 */
import { useMemo, useState } from 'react';
import { api } from '../api';
import { l3Api } from '../l3';
import { BarList, Kpi, OutcomeStack, TrendChart } from '../components/Charts';
import { EMOTION_TEXT, count, defaultWindow, ms, percent, reasonText } from '../format';
import { useAsync } from '../useAsync';

const DIMS = [
  { key: 'category', label: '品类' }, { key: 'sku', label: '型号' }, { key: 'plan', label: '官方 Q&A' },
  { key: 'reason', label: '结局原因' }, { key: 'emotion', label: '情绪' },
] as const;
const RANGES = [{ days: 1, label: '今天' }, { days: 7, label: '近 7 天' }, { days: 30, label: '近 30 天' }, { days: 365, label: '近一年' }];

function num(value: number | string | undefined): number { return Number(value ?? 0) || 0; }

export function Board() {
  const [days, setDays] = useState(7);
  const [dim, setDim] = useState<string>('category');
  // 必须记忆：直接在渲染里算 Date.now() 会让每次渲染都得到新的 from，进而无限触发重新取数。
  const from = useMemo(() => defaultWindow(days).from, [days]);
  const bucket = days <= 1 ? 'hour' : 'day';

  const overview = useAsync(() => api.overview({ from, bucket, dim }), [from, bucket, dim]);
  const byReason = useAsync(() => api.overview({ from, bucket, dim: 'reason' }), [from, bucket]);
  const byEmotion = useAsync(() => api.overview({ from, bucket, dim: 'emotion' }), [from, bucket]);
  const l3 = useAsync(() => l3Api.metrics(from), [from]);

  if (overview.error) return <p className="empty">读取失败：{overview.error}</p>;
  const data = overview.data;
  const totals = data?.totals ?? {};
  const latency = data?.latency ?? {};
  const sessions = num(totals.sessions);
  const reasonOf = (key: string) => byReason.data?.breakdown.find((b) => b.value === key)?.sessions ?? 0;
  // 后端把没有情绪记录的会话记作「(未知)」（analytics/queries.py），不能算进「非平静」。
  const emotions = (byEmotion.data?.breakdown ?? []).filter((b) => b.value && b.value !== '(未知)');
  const emotionTotal = emotions.reduce((acc, b) => acc + b.sessions, 0);
  const notCalm = emotions.filter((b) => b.value !== 'calm').reduce((acc, b) => acc + b.sessions, 0);
  const modelCalls = (data?.models ?? []).reduce((acc, m) => acc + m.calls, 0);
  const fallbacks = (data?.models ?? []).reduce((acc, m) => acc + m.fallbacks, 0);
  const retrievalTotal = (data?.retrieval ?? []).reduce((acc, r) => acc + r.n, 0);
  const noMatch = (data?.retrieval ?? []).filter((r) => r.status === 'no_match').reduce((acc, r) => acc + r.n, 0);
  const ratio = (a: number, b: number) => (b > 0 ? a / b : null);

  return (
    <>
      <div className="filters">
        {RANGES.map((r) => (
          <button key={r.days} className="btn" data-variant={days === r.days ? 'primary' : undefined} onClick={() => setDays(r.days)}>{r.label}</button>
        ))}
        <span className="muted" style={{ fontSize: 12 }}>{overview.loading ? '加载中…' : `${count(sessions)} 个会话 · ${count(l3.data?.episodes)} 个问题`}</span>
        <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>会话级指标暂未剔除回放 / 冒烟流量（P2）</span>
      </div>

      <h2 className="row-title">业务 <span>按问题（episode）计；剔除回放 / 冒烟</span></h2>
      {l3.error && <p className="empty">L3 指标读取失败：{l3.error}</p>}
      <div className="grid kpis" style={{ marginBottom: 18 }}>
        <Kpi label="独立托管率" value={percent(l3.data?.managed_rate)} hint="独立解决 + 独立闭环 + 咨询回答 ÷ 所有终态（含转人工、放弃）。申请提交仍在跟踪，不算闭环。" note={`完成 ${count(l3.data?.managed)} / 终态 ${count(l3.data?.terminal)}`} />
        <Kpi label="净满意度 NSS" value={percent(l3.data?.nss)} hint="4–5 分占比减 1–2 分占比；3 分中性。评分不改变案件状态。" note={`评分覆盖率 ${percent(l3.data?.rating_coverage)}`} />
        <Kpi label="意图准确率" value={percent(l3.data?.intent_accuracy)} hint="人工标注意图正确 ÷ 已标注；无标注时暂无数据。" note={`已标注 ${count(l3.data?.intent_labeled)}`} />
        <Kpi label="越权执行" value={l3.data?.unauthorized_executions == null ? '—' : count(l3.data.unauthorized_executions)} hint="写动作成功但四项授权检查不完整或任一失败的次数；目标为 0。" />
      </div>

      <h2 className="row-title">五个难点 <span>看图 · 问清 · 分流 · 接稳 · 幻觉</span></h2>
      <div className="grid kpis five" style={{ marginBottom: 18 }}>
        <Kpi label="看图 · 读图可用率" value="—" hint="可用图片 ÷ 上传图片。节点级 vision_status 已落库，聚合查询待接（P2）。" note="待接数据" />
        <Kpi label="问清 · 澄清超限率" value={percent(ratio(reasonOf('R7'), sessions))} hint="因澄清超限（R7）转人工的会话 ÷ 会话数；越低说明追问越准。" note={`平均排障步骤 ${totals.avg_steps ?? '—'}`} />
        <Kpi label="分流 · 政策类升级" value={percent(ratio(reasonOf('R3') + reasonOf('R8'), sessions))} hint="用户要人工（R3）与范围外（R8）÷ 会话数：分流出去而不是系统失败的部分。" note={`要人工 ${count(reasonOf('R3'))} · 范围外 ${count(reasonOf('R8'))}`} />
        <Kpi label="接稳 · 非平静情绪占比" value={percent(ratio(notCalm, emotionTotal))} hint="会话最近一轮记录的情绪不是「平静」的占比（没有情绪记录的会话不计）；分级处理是否生效看旅程页的情绪轨迹。" note={emotions.slice(0, 3).map((b) => `${EMOTION_TEXT[b.value] ?? b.value} ${b.sessions}`).join(' · ') || '—'} />
        <Kpi label="幻觉 · 检索无命中率" value={percent(ratio(noMatch, retrievalTotal))} hint="检索无命中 ÷ 检索次数：没有依据时系统必须诚实升级而不是编。越权执行见业务行。" note={`无命中 ${count(noMatch)} / ${count(retrievalTotal)}`} />
      </div>

      <h2 className="row-title">体验与性能 <span>按会话 / run 计</span></h2>
      <div className="grid kpis" style={{ marginBottom: 18 }}>
        <Kpi label="首次可见 P95" value={ms(latency.first_visible_p95)} hint="从收到消息到第一段可见文字。" note={`中位 ${ms(latency.first_visible_p50)}`} />
        <Kpi label="首张卡片 P95" value={ms(latency.card_ready_p95)} hint="从收到消息到第一张卡片。" note={`中位 ${ms(latency.card_ready_p50)}`} />
        <Kpi label="模型降级率" value={percent(ratio(fallbacks, modelCalls))} hint="最终模型不是链首模型的调用占比。" note={`${count(modelCalls)} 次调用 · ${count(num(totals.tokens_in))} + ${count(num(totals.tokens_out))} tok`} />
        <Kpi label="会话结局" value={`${count(num(totals.resolved))} 解决 / ${count(num(totals.escalated))} 转人工`} hint="会话口径的解决与转人工数；比率见下方结局构成。" note={`放弃 ${count(num(totals.abandoned))} · 出错 ${count(num(totals.errored))}`} />
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
          <OutcomeStack totals={Object.fromEntries(Object.entries(totals).map(([k, v]) => [k, num(v)]))} />
        </div>
      </div>

      <div className="card">
        <h2>分布</h2>
        <p className="sub">按维度看会话都落在哪里。</p>
        <div className="filters">
          {DIMS.map((d) => <button key={d.key} className="chip" aria-pressed={dim === d.key} onClick={() => setDim(d.key)}>{d.label}</button>)}
        </div>
        <BarList rows={(data?.breakdown ?? []).slice(0, 10).map((b) => ({
          value: dim === 'reason' ? reasonText(b.value) : dim === 'emotion' ? (EMOTION_TEXT[b.value] ?? b.value) : b.value, sessions: b.sessions,
        }))} />
      </div>
    </>
  );
}
