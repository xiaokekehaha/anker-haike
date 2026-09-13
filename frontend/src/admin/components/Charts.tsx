/** 图表：手写 SVG，不引图表库（管理端首包只为 DAG 付一次依赖成本）。
 *  形式按 dataviz 的「数据的职责决定形式」：
 *  - 单个数字 → 统计块（Kpi），不做成一根条；
 *  - 随时间变化 → 折线，两系列用分类槽 1/2（已通过校验器）；
 *  - 比较大小 → 单色横条，长度编码大小；
 *  - 部分与整体 → 一根水平堆叠条，每段都有文字标签。
 *  颜色一律不单独表意：徽标、图例、段标签都带文字。 */
import type { ReactNode } from 'react';
import { count, dayLabel, outcomeLabel, outcomeRole, STACK_ORDER, type Role } from '../format';
import type { Outcome } from '../types';

export function Kpi({ label, value, note, hint }: { label: string; value: ReactNode; note?: ReactNode; hint?: string }) {
  return (
    <div className="card kpi">
      <div className="label" title={hint}>{label}</div>
      <div className="value">{value}</div>
      {note !== undefined && <div className="note">{note}</div>}
    </div>
  );
}

export function Badge({ outcome }: { outcome: string }) {
  const role = outcomeRole(outcome);
  return (
    <span className="badge">
      <i className={`role-${role}`} aria-hidden="true" />
      {outcomeLabel(outcome)}
    </span>
  );
}

type Series = { key: string; label: string; color: string; values: number[] };

/** 折线：≥2 系列必带图例；只在最后一点直接标注，不给每个点标数字。 */
export function TrendChart({ labels, series, height = 190 }: { labels: string[]; series: Series[]; height?: number }) {
  if (!labels.length) return <p className="empty">这个时间窗里没有数据</p>;
  const width = 720;
  const pad = { top: 14, right: 46, bottom: 26, left: 38 };
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (labels.length === 1 ? innerW / 2 : (i * innerW) / (labels.length - 1));
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const ticks = [0, Math.round(max / 2), max];
  // 轴标签太密时抽稀
  const step = Math.ceil(labels.length / 8);

  return (
    <>
      <div className="legend">
        {series.map((s) => (
          <span key={s.key}><i style={{ background: s.color }} aria-hidden="true" />{s.label}</span>
        ))}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img"
        aria-label={`趋势图：${series.map((s) => s.label).join('、')}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth="1" />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">{t}</text>
          </g>
        ))}
        {labels.map((label, i) => (i % step === 0 ? (
          <text key={label + i} x={x(i)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--muted)">
            {dayLabel(label)}
          </text>
        ) : null))}
        {series.map((s) => {
          const d = s.values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
          const last = s.values.length - 1;
          const lastValue = s.values[last] ?? 0;
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
              {s.values.length === 1 && <circle cx={x(0)} cy={y(s.values[0] ?? 0)} r="4" fill={s.color} />}
              {/* 只标最后一点，避免每点都是数字 */}
              <text x={x(last) + 7} y={y(lastValue) + 4} fontSize="10.5" fill="var(--muted)">
                {lastValue}
              </text>
            </g>
          );
        })}
      </svg>
    </>
  );
}

/** 单序列横条：同一种蓝，长度编码大小。名称 + 数值都是文字。 */
export function BarList({ rows, total, unit = '' }: { rows: { value: string; sessions: number }[]; total?: number; unit?: string }) {
  if (!rows.length) return <p className="empty">没有数据</p>;
  const max = Math.max(...rows.map((r) => r.sessions), 1);
  const sum = total ?? rows.reduce((acc, r) => acc + r.sessions, 0);
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={row.value}>
          <span className="name" title={row.value}>{row.value}</span>
          <span className="track"><span className="fill" style={{ width: `${(row.sessions / max) * 100}%` }} /></span>
          <span className="n">{count(row.sessions)}{unit}{sum > 0 && ` · ${((row.sessions / sum) * 100).toFixed(0)}%`}</span>
        </div>
      ))}
    </div>
  );
}

const ROLE_CLASS: Record<Role, string> = {
  good: 'role-good', warning: 'role-warning', critical: 'role-critical',
  serious: 'role-serious', neutral: 'role-neutral',
};

/** 结局构成：一根水平堆叠条。段顺序固定为 good → warning → critical → serious → neutral，
 *  这个相邻顺序通过了 CVD 与常视觉分辨检查；每段在下方都有「色块 + 名称 + 数量」。 */
export function OutcomeStack({ totals }: { totals: Record<string, number> }) {
  const entries = STACK_ORDER
    .map((key) => ({ key, n: Number(totals[key] ?? 0) }))
    .filter((e) => e.n > 0);
  const sum = entries.reduce((acc, e) => acc + e.n, 0);
  if (!sum) return <p className="empty">这个时间窗里没有会话</p>;
  return (
    <>
      <div className="stack" role="img" aria-label={`结局构成：${entries.map((e) => `${outcomeLabel(e.key)} ${e.n}`).join('，')}`}>
        {entries.map((e) => (
          <span key={e.key} className={ROLE_CLASS[outcomeRole(e.key)]} style={{ width: `${(e.n / sum) * 100}%` }} />
        ))}
      </div>
      <div className="stack-legend">
        {entries.map((e) => (
          <span key={e.key}>
            <i className={`${ROLE_CLASS[outcomeRole(e.key)]}`}
              style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 3, marginRight: 6 }} aria-hidden="true" />
            {outcomeLabel(e.key)} <b>{e.n}</b>
          </span>
        ))}
      </div>
    </>
  );
}

export function outcomeTotals(totals: Record<string, number>): Record<Outcome, number> {
  return totals as Record<Outcome, number>;
}
