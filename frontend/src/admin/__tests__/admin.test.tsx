/** Phase 3 组件测试：路径高亮、瀑布排序、口径文案、堆叠顺序。
 *  React Flow 在 jsdom 里没有真实尺寸，渲染桩掉，只断言我们传给它的 nodes / edges。 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

const flowProps: { nodes: any[]; edges: any[] }[] = [];
vi.mock('@xyflow/react', () => ({
  ReactFlow: (props: any) => {
    flowProps.push({ nodes: props.nodes, edges: props.edges });
    return <div data-testid="flow" />;
  },
  Background: () => null,
  Controls: () => null,
  Position: { Left: 'left', Right: 'right' },
}));
vi.mock('@xyflow/react/dist/style.css', () => ({}));

const { GraphView } = await import('../components/GraphView');
const { RunWaterfall } = await import('../components/RunWaterfall');
const { OutcomeStack, Badge, TrendChart, BarList } = await import('../components/Charts');
const { ms, percent, outcomeLabel, reasonText, STACK_ORDER } = await import('../format');

const TOPOLOGY = {
  nodes: [
    { id: '__start__', stage: 'start' }, { id: 'intake', stage: 'intake' },
    { id: 'disambiguate', stage: 'disambiguate' }, { id: 'retrieve', stage: 'diagnose' },
    { id: 'guide', stage: 'guide' }, { id: 'await_input', stage: 'wait' },
  ],
  edges: [
    { source: '__start__', target: 'intake', conditional: true },
    { source: 'intake', target: 'disambiguate', conditional: true },
    { source: 'disambiguate', target: 'retrieve', conditional: true },
    { source: 'retrieve', target: 'guide', conditional: false },
    { source: 'guide', target: 'await_input', conditional: false },
  ],
  stage_order: ['start', 'intake', 'disambiguate', 'diagnose', 'guide', 'wait'],
};

function lastFlow() {
  return flowProps[flowProps.length - 1]!;
}

describe('GraphView', () => {
  test('把走过的边高亮、没走过的压暗', () => {
    render(<GraphView topology={TOPOLOGY} path={['intake', 'disambiguate', 'retrieve']} />);
    const { edges } = lastFlow();
    const walked = edges.find((e: any) => e.id === 'intake->disambiguate');
    const notWalked = edges.find((e: any) => e.id === 'retrieve->guide');
    expect(walked.animated).toBe(true);
    expect(walked.style.opacity).toBe(1);
    expect(notWalked.animated).toBe(false);
    expect(notWalked.style.opacity).toBeLessThan(1);
  });

  test('节点按阶段分列，列序与 stage_order 一致', () => {
    render(<GraphView topology={TOPOLOGY} />);
    const { nodes } = lastFlow();
    const x = (id: string) => nodes.find((n: any) => n.id === id).position.x;
    expect(x('__start__')).toBeLessThan(x('intake'));
    expect(x('intake')).toBeLessThan(x('disambiguate'));
    expect(x('disambiguate')).toBeLessThan(x('retrieve'));
    expect(x('retrieve')).toBeLessThan(x('guide'));
  });

  test('同一节点走过两次时标第一次的序号', () => {
    render(<GraphView topology={TOPOLOGY} path={['intake', 'disambiguate', 'intake']} />);
    const { nodes } = lastFlow();
    const intake = nodes.find((n: any) => n.id === 'intake');
    const { getByText } = render(<>{intake.data.label}</>);
    expect(getByText('1')).toBeInTheDocument();
  });

  test('聚合模式下边宽随经过次数增长，没走过的边最细', () => {
    render(<GraphView topology={TOPOLOGY} traffic={{
      edges: [{ source: 'intake', target: 'disambiguate', n: 100 }, { source: 'retrieve', target: 'guide', n: 5 }],
      nodes: [{ node: 'intake', n: 100, errors: 0, interrupts: 0, p50_ms: 900 }],
      entries: [],
    }} />);
    const { edges } = lastFlow();
    const busy = edges.find((e: any) => e.id === 'intake->disambiguate').style.strokeWidth;
    const quiet = edges.find((e: any) => e.id === 'retrieve->guide').style.strokeWidth;
    const unused = edges.find((e: any) => e.id === 'guide->await_input').style.strokeWidth;
    expect(busy).toBeGreaterThan(quiet);
    expect(quiet).toBeGreaterThan(unused);
  });
});

const NODES = [
  { run_id: 'r1', idx: 1, node: 'intake', prev_node: null, started_at: '', duration_ms: 2500, status: 'ok' as const, summary: null },
  { run_id: 'r1', idx: 2, node: 'retrieve', prev_node: 'intake', started_at: '', duration_ms: 500, status: 'ok' as const, summary: null },
  { run_id: 'r1', idx: 3, node: 'await_input', prev_node: 'retrieve', started_at: '', duration_ms: 100, status: 'interrupt' as const, summary: null },
];

describe('RunWaterfall', () => {
  test('按顺序列出节点，并把耗时与宽度对应', () => {
    const { container } = render(
      <RunWaterfall nodes={NODES} models={[]} retrievals={[]} selected={null} onSelect={() => {}} />,
    );
    const names = [...container.querySelectorAll('.wf-row .name')].map((n) => n.textContent);
    expect(names[0]).toContain('理解诉求');
    expect(names[1]).toContain('检索知识');
    expect(names[2]).toContain('等待用户');
    const fills = [...container.querySelectorAll('.fill')] as HTMLElement[];
    // intake 占 2500/3100，明显比 retrieve 的 500/3100 宽
    expect(parseFloat(fills[0]!.style.width)).toBeGreaterThan(parseFloat(fills[1]!.style.width));
  });

  test('把模型调用与检索挂到对应节点下', () => {
    render(
      <RunWaterfall nodes={NODES} selected={null} onSelect={() => {}}
        models={[{ run_id: 'r1', node: 'intake', task: 'intake', model_used: 'deepseek/chat', lane: 'domestic', status: 'ok', attempts: 1, fallback_used: true, stream: false, latency_ms: 2400, tokens_in: 600, tokens_out: 40, error_type: null, created_at: '' }]}
        retrievals={[{ run_id: 'r1', node: 'retrieve', round: 1, kb: 'kb_manual', status: 'ok', allowed_count: 2, hits: 5, top_score: 0.02, latency_ms: 240, query: null, created_at: '' }]} />,
    );
    expect(screen.getByText(/deepseek\/chat/)).toHaveTextContent('已降级');
    expect(screen.getByText(/kb_manual/)).toHaveTextContent('命中 5');
  });

  test('历史回填没有耗时时说明条形只表示顺序', () => {
    render(<RunWaterfall selected={null} onSelect={() => {}} models={[]} retrievals={[]}
      nodes={NODES.map((n) => ({ ...n, duration_ms: null }))} />);
    expect(screen.getByText(/仅表示顺序/)).toBeInTheDocument();
  });

  test('没有节点轨迹时给出原因而不是空白', () => {
    render(<RunWaterfall nodes={[]} models={[]} retrievals={[]} selected={null} onSelect={() => {}} />);
    expect(screen.getByText(/没有节点轨迹/)).toBeInTheDocument();
  });
});

describe('图表与口径', () => {
  test('结局构成按固定顺序堆叠，且每段都有文字标签', () => {
    const { container } = render(<OutcomeStack totals={{ resolved: 6, escalated: 3, errored: 1, abandoned: 2 }} />);
    const classes = [...container.querySelectorAll('.stack > span')].map((s) => s.className);
    // good → warning → critical → serious：这个相邻顺序通过了 CVD 与常视觉分辨检查
    expect(classes).toEqual(['role-good', 'role-warning', 'role-critical', 'role-serious']);
    const legend = container.querySelector('.stack-legend')!;
    expect(within(legend as HTMLElement).getByText('已解决')).toBeInTheDocument();
    expect(within(legend as HTMLElement).getByText('已转人工')).toBeInTheDocument();
  });

  test('堆叠顺序常量与渲染顺序一致', () => {
    expect(STACK_ORDER.slice(0, 4)).toEqual(['resolved', 'escalated', 'errored', 'abandoned']);
  });

  test('徽标同时给出颜色与文字', () => {
    const { container } = render(<Badge outcome="escalated" />);
    expect(container.querySelector('.role-warning')).toBeTruthy();
    expect(screen.getByText('已转人工')).toBeInTheDocument();
  });

  test('两系列折线一定带图例', () => {
    const { container } = render(
      <TrendChart labels={['2026-09-12T00:00:00Z', '2026-09-13T00:00:00Z']} series={[
        { key: 'a', label: '会话数', color: 'red', values: [3, 5] },
        { key: 'b', label: '已解决', color: 'blue', values: [1, 2] },
      ]} />,
    );
    expect(container.querySelectorAll('.legend span')).toHaveLength(2);
    expect(screen.getByText('会话数')).toBeInTheDocument();
  });

  test('没有数据时说明而不是画空图', () => {
    render(<TrendChart labels={[]} series={[]} />);
    expect(screen.getByText(/没有数据/)).toBeInTheDocument();
  });

  test('横条按最大值归一，并给出占比', () => {
    const { container } = render(<BarList rows={[{ value: '扫地机', sessions: 80 }, { value: '吸奶器', sessions: 20 }]} />);
    const fills = [...container.querySelectorAll('.fill')] as HTMLElement[];
    expect(fills[0]!.style.width).toBe('100%');
    expect(fills[1]!.style.width).toBe('25%');
    expect(screen.getByText(/80 · 80%/)).toBeInTheDocument();
  });

  test('比率为 null 时显示破折号，不显示 0%', () => {
    expect(percent(null)).toBe('—');
    expect(percent(0)).toBe('0.0%');
    expect(percent(0.1579)).toBe('15.8%');
  });

  test('耗时按量级换单位', () => {
    expect(ms(null)).toBe('—');
    expect(ms(240)).toBe('240 ms');
    expect(ms(2530)).toBe('2.5 s');
    expect(ms(72000)).toBe('72 s');
  });

  test('结局与规则号翻成人话', () => {
    expect(outcomeLabel('resolved')).toBe('已解决');
    expect(outcomeLabel('interrupted')).toBe('被打断');
    expect(reasonText('R5')).toBe('知识库不可用');
    expect(reasonText(null)).toBe('—');
    expect(reasonText('R99')).toBe('R99');
  });
});
