import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EscalationSummary } from '../types/snapshot';
import { SummaryCard, summaryToText } from './SummaryCard';

const summary: EscalationSummary = {
  product: 'eufy X10 Pro Omni', problem: '不能启动', observations: ['放回基站后有充电提示（指示灯或语音）吗？没有充电提示'], hypotheses: ['无法启动或充电时的基站供电与充电检查'],
  steps: [
    { step_id: 's1', title: '检查基站供电与触点', feedback: 'not_solved', observed: ['电源灯亮'] },
    { step_id: 's2', title: '放回基站观察充电', feedback: 'not_solved', observed: ['没有充电提示'] },
  ],
  reason: { rule_id: 'R2', text: '已操作但未解决「检查基站供电与触点」、「放回基站观察充电」，现有资料没有进一步可执行的排查操作', cause: 'no_supported_followup' },
  emotion: { level: 'calm', strategy: 'normal' },
  receipt: { status: 'not_collected', verified_facts: {}, conflicts: [] },
  model_trace: [],
};

describe('SummaryCard 的真实结束原因（design §3.5）', () => {
  it('展示真实原因文字与观察结果，规则码只是附注；prepared 不显示成已接入', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="prepared" />);
    expect(container.querySelector('[data-kind="end-reason"]')).toHaveTextContent('现有资料没有进一步可执行的排查操作');
    expect(container.querySelector('[data-kind="end-reason"]')).toHaveTextContent('no_supported_followup');
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('已整理记录，尚未接入人工');
    expect(screen.getByText(/观察：没有充电提示/)).toBeInTheDocument();
    expect(summaryToText(summary)).toContain('放回基站观察充电（已操作，仍有问题；观察：没有充电提示）');
  });

  it('无法操作的步骤在页面和剪贴板都保留真实反馈，不称为已执行', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const skipped: EscalationSummary = {
      ...summary,
      product: '扫地机器人（型号未确认）',
      problem: '扫地机回不了基站',
      observations: ['插上设备后没有输出反应'],
      hypotheses: ['输出接口或连接问题'],
      steps: [
        { step_id: 's1', title: '清洁基站充电触点', feedback: 'cannot_do' },
        { step_id: 's2', title: '更换数据线和被充设备测试', feedback: 'cannot_do' },
      ],
      reason: { rule_id: 'R2', text: '两项操作均无法完成，已整理排查记录', cause: 'no_supported_followup' },
    };
    const { container } = render(<SummaryCard summary={skipped} />);
    expect(screen.getByText('排查记录')).toBeVisible();
    expect(container).toHaveTextContent('清洁基站充电触点（无法操作）');
    expect(container).not.toHaveTextContent('已执行步骤');
    expect(container).not.toHaveTextContent('cannot_do');
    fireEvent.click(screen.getByRole('button', { name: '一键复制' }));
    await screen.findByText('已复制');
    expect(writeText).toHaveBeenCalledWith(summaryToText(skipped));
    expect(summaryToText(skipped)).toContain('【排查记录】清洁基站充电触点（无法操作）');
    expect(summaryToText(skipped)).not.toMatch(/已执行步骤|cannot_do/);
  });

  it('accepted 才显示人工已接单', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="accepted" />);
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('人工已接单');
  });
});
