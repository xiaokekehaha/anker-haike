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
const sessions = vi.fn();
const metrics = vi.fn();
const queue = vi.fn();

vi.mock('../api', () => ({
  api: {
    overview: (...args: unknown[]) => overview(...args),
    flow: vi.fn(),
    topology: vi.fn(),
    sessions: (...args: unknown[]) => sessions(...args),
    journey: vi.fn(),
    reviews: vi.fn(),
    labelReview: vi.fn(),
    patchReview: vi.fn(),
  },
}));
vi.mock('../l3', () => ({
  l3Api: {
    metrics: (...args: unknown[]) => metrics(...args),
    queue: (...args: unknown[]) => queue(...args),
  },
}));

const { Board } = await import('../pages/Board');
const { Sessions } = await import('../pages/Sessions');

const OVERVIEW = {
  window: { from: '', to: '', bucket: 'day' },
  totals: { sessions: 12, resolved: 5, escalated: 3, escalated_system: 1, abandoned: 2, errored: 0, model_calls: 40, tokens_in: 1, tokens_out: 2, avg_steps: '1.5' },
  latency: { first_visible_p50: 100, first_visible_p95: 900, card_ready_p50: 200, card_ready_p95: 1800 },
  rates: { self_service: 0.83, closure: 0.62, escalation: 0.38 },
  series: [{ at: '2026-09-12T00:00:00Z', sessions: 7, resolved: 3, escalated: 1 }],
  breakdown: [{ value: 'robot_vacuum', sessions: 9, resolved: 4, escalated: 2 }],
  models: [{ task: 'intake', model_used: 'deepseek/chat', calls: 20, errors: 0, fallbacks: 1, p95_ms: 2400, tokens_in: 1, tokens_out: 2 }],
  retrieval: [{ kb: 'kb_qa', status: 'ok', n: 10 }, { kb: 'kb_qa', status: 'no_match', n: 30 }],
};
const L3 = { episodes: 10, terminal: 5, managed: 4, managed_rate: 0.8, rated: 2, rating_coverage: 0.2, nss: 0.5, intent_labeled: 0, intent_accuracy: null, unauthorized_executions: 0 };

beforeEach(() => {
  overview.mockReset().mockResolvedValue(OVERVIEW);
  sessions.mockReset().mockResolvedValue({ items: [], next_cursor: null });
  metrics.mockReset().mockResolvedValue(L3);
  queue.mockReset().mockResolvedValue({ items: [] });
});

describe('Board', () => {
  test('一个时间窗只取一次数，不会反复重取', async () => {
    render(<MemoryRouter><Board /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('80.0%')).toBeInTheDocument());
    // 给潜在的循环留出反复触发的机会
    await new Promise((resolve) => setTimeout(resolve, 120));
    // 三个维度（当前维度 / 原因 / 情绪）各取一次，L3 一次；StrictMode 不在测试里启用
    expect(overview).toHaveBeenCalledTimes(3);
    expect(metrics).toHaveBeenCalledTimes(1);
  });

  test('把口径与单位按人话显示，且口径写在卡片上', async () => {
    render(<MemoryRouter><Board /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('80.0%')).toBeInTheDocument());
    expect(screen.getByText('900 ms')).toBeInTheDocument();
    expect(screen.getByText('1.8 s')).toBeInTheDocument();
    expect(screen.getByText('5 解决 / 3 转人工')).toBeInTheDocument();
    // 模型降级率 1 / 20；检索无命中率 30 / 40
    expect(screen.getByText('5.0%')).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument();
    expect(screen.getByText(/独立解决 \+ 独立闭环/)).toBeVisible();
  });

  test('没有情绪记录的会话不算作非平静', async () => {
    const row = (value: string, n: number) => ({ value, sessions: n, resolved: 0, escalated: 0 });
    overview.mockImplementation(async ({ dim }: { dim: string }) =>
      dim === 'emotion' ? { ...OVERVIEW, breakdown: [row('calm', 3), row('(未知)', 5), row('angry', 1)] } : OVERVIEW);
    render(<MemoryRouter><Board /></MemoryRouter>);
    // 1 个愤怒 ÷（3 平静 + 1 愤怒）；把「(未知)」算进来会得到 6 / 9。
    await waitFor(() => expect(screen.getByText('25.0%')).toBeInTheDocument());
    expect(screen.queryByText('66.7%')).not.toBeInTheDocument();
  });
});

describe('Sessions', () => {
  test('一个筛选条件只取一次数', async () => {
    render(<MemoryRouter><Sessions /></MemoryRouter>);
    await waitFor(() => expect(sessions).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(sessions).toHaveBeenCalledTimes(1);
    expect(queue).toHaveBeenCalledTimes(1);
  });

  test('没有结果时给出说明而不是空表', async () => {
    render(<MemoryRouter><Sessions /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/这个条件下没有会话/)).toBeInTheDocument());
  });
});
