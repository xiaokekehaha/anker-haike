/** 页面级回归：取数不能成环。
 *  曾经在渲染里直接算 Date.now() 当时间窗，导致每次渲染都换出新的请求参数，
 *  useAsync 依赖随之变化 → 无限重取（实测对后端打出 500 次请求）。 */
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@xyflow/react', () => ({
  ReactFlow: () => <div data-testid="flow" />,
  Background: () => null,
  Controls: () => null,
  Position: { Left: 'left', Right: 'right' },
}));
vi.mock('@xyflow/react/dist/style.css', () => ({}));

const overview = vi.fn();
const flow = vi.fn();
const topology = vi.fn();
const sessions = vi.fn();

vi.mock('../api', () => ({
  api: {
    overview: (...args: unknown[]) => overview(...args),
    flow: (...args: unknown[]) => flow(...args),
    topology: (...args: unknown[]) => topology(...args),
    sessions: (...args: unknown[]) => sessions(...args),
    journey: vi.fn(),
    cases: vi.fn(),
    labelCase: vi.fn(),
    patchCase: vi.fn(),
  },
}));

const { Dashboard } = await import('../pages/Dashboard');
const { Sessions } = await import('../pages/Sessions');

const OVERVIEW = {
  window: { from: '', to: '', bucket: 'day' },
  totals: { sessions: 12, resolved: 5, escalated: 3, escalated_system: 1, model_calls: 40, tokens_in: 1, tokens_out: 2 },
  latency: { first_visible_p50: 100, first_visible_p95: 900, card_ready_p50: 200, card_ready_p95: 1800 },
  rates: { self_service: 0.83, closure: 0.62, escalation: 0.38 },
  series: [{ at: '2026-09-12T00:00:00Z', sessions: 7, resolved: 3, escalated: 1 }],
  breakdown: [{ value: 'robot_vacuum', sessions: 9, resolved: 4, escalated: 2 }],
  models: [{ task: 'intake', model_used: 'deepseek/chat', calls: 20, errors: 0, fallbacks: 1, p95_ms: 2400, tokens_in: 1, tokens_out: 2 }],
  retrieval: [{ kb: 'kb_manual', status: 'ok', n: 10 }],
};

beforeEach(() => {
  overview.mockReset().mockResolvedValue(OVERVIEW);
  flow.mockReset().mockResolvedValue({ edges: [], nodes: [], entries: [] });
  topology.mockReset().mockResolvedValue({ nodes: [], edges: [], stage_order: [] });
  sessions.mockReset().mockResolvedValue({ items: [], next_cursor: null });
});

describe('Dashboard', () => {
  test('一个时间窗只取一次数，不会反复重取', async () => {
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('83.0%')).toBeInTheDocument());
    // 给潜在的循环留出反复触发的机会
    await new Promise((resolve) => setTimeout(resolve, 120));
    // StrictMode 不在测试里启用，因此每个数据源恰好一次
    expect(overview).toHaveBeenCalledTimes(1);
    expect(flow).toHaveBeenCalledTimes(1);
    expect(topology).toHaveBeenCalledTimes(1);
  });

  test('把口径与单位按人话显示', async () => {
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('83.0%')).toBeInTheDocument());
    expect(screen.getByText('62.0%')).toBeInTheDocument();
    expect(screen.getByText('900 ms')).toBeInTheDocument();
    expect(screen.getByText('1.8 s')).toBeInTheDocument();
    expect(screen.getByText('已解决 5 个')).toBeInTheDocument();
  });
});

describe('Sessions', () => {
  test('一个筛选条件只取一次数', async () => {
    render(<MemoryRouter><Sessions /></MemoryRouter>);
    await waitFor(() => expect(sessions).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(sessions).toHaveBeenCalledTimes(1);
  });

  test('没有结果时给出说明而不是空表', async () => {
    render(<MemoryRouter><Sessions /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/这个条件下没有会话/)).toBeInTheDocument());
  });
});
