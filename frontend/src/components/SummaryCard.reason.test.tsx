import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { EscalationSummary } from '../types/snapshot';
import { SummaryCard, summaryToText } from './SummaryCard';

const summary: EscalationSummary = {
  product: 'eufy X10 Pro Omni', problem: '不能启动', observations: ['放回基站后有充电提示（指示灯或语音）吗？没有充电提示'], hypotheses: ['无法启动或充电时的基站供电与充电检查'],
  steps: [
    { step_id: 's1', title: '检查基站供电与触点', feedback: 'not_solved', observed: ['电源灯亮'] },
    { step_id: 's2', title: '放回基站观察充电', feedback: 'not_solved', observed: ['没有充电提示'] },
  ],
  reason: { rule_id: 'R2', text: '已完成「检查基站供电与触点」、「放回基站观察充电」，现有资料没有进一步可执行的排查操作', cause: 'no_supported_followup' },
  emotion: { level: 'calm', strategy: 'normal' },
  receipt: { status: 'not_collected', verified_facts: {}, conflicts: [] },
  model_trace: [],
} as unknown as EscalationSummary;

describe('SummaryCard 的真实结束原因（design §3.5）', () => {
  it('展示真实原因文字与观察结果，规则码只是附注；prepared 不显示成已接入', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="prepared" />);
    expect(container.querySelector('[data-kind="end-reason"]')).toHaveTextContent('现有资料没有进一步可执行的排查操作');
    expect(container.querySelector('[data-kind="end-reason"]')).toHaveTextContent('no_supported_followup');
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('已整理记录，尚未接入人工');
    expect(screen.getByText(/观察：没有充电提示/)).toBeInTheDocument();
    expect(summaryToText(summary)).toContain('放回基站观察充电（not_solved；观察：没有充电提示）');
  });

  it('accepted 才显示人工已接单', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="accepted" />);
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('人工已接单');
  });
});
