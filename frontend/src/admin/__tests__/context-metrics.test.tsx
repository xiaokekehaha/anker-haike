import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { NodeDetail } from '../components/NodeDetail';
import type { NodeRun } from '../types';

const node: NodeRun = {
  run_id: 'r', idx: 1, node: 'understand', prev_node: null, started_at: '',
  duration_ms: 100, status: 'ok', summary: { context_metrics: [
    { event: 'context_built', task: 'intake', tokens: 5200, max_tokens: 13000,
      token_breakdown: { system: 2000, authority: 2200, current: 100, history: 900 },
      omitted_entries: 8, truncated: false, cache_dropped: true },
    { event: 'model_call', model: 'fake', actual_input_tokens: 6100,
      attempts: [{ alias: 'test', outcome: 'ok', estimated_input_tokens: 8000, input_budget: 16000 }] },
  ] },
};

describe('上下文观测', () => {
  test('显示各块预算、裁剪、含 Schema 估算和厂商实际输入', () => {
    render(<NodeDetail node={node} models={[]} retrievals={[]} />);
    expect(screen.getByText(/5,200 \/ 13,000/)).toBeInTheDocument();
    expect(screen.getByText('状态事实')).toBeInTheDocument();
    expect(screen.getByText(/未纳入历史 8 条/)).toHaveTextContent('摘录缓存移除 是');
    expect(screen.getByText(/实际输入 6,100/)).toBeInTheDocument();
    expect(screen.getByText(/估算输入（含 Schema）8,000 \/ 16,000/)).toBeInTheDocument();
    expect(screen.queryByText(/没有留下额外判定信息/)).not.toBeInTheDocument();
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
  });

  test('预算拒绝没有模型用量时不显示为零', () => {
    render(<NodeDetail node={{ ...node, summary: { context_metrics: [
      { event: 'context_budget', task: 'intake', required_tokens: 18000, max_tokens: 13000 },
      { event: 'model_call', attempts: [] },
    ] } }} models={[]} retrievals={[]} />);
    expect(screen.getByText(/必需内容超限/)).toBeInTheDocument();
    expect(screen.getByText(/实际输入 — tok/)).toBeInTheDocument();
  });

  test('历史节点缺少指标仍可打开', () => {
    render(<NodeDetail node={{ ...node, summary: null }} models={[]} retrievals={[]} />);
    expect(screen.queryByRole('region', { name: '上下文预算' })).not.toBeInTheDocument();
    expect(screen.getByText(/没有留下额外判定信息/)).toBeInTheDocument();
  });
});
