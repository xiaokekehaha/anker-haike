import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EscalationSummary } from '../types/snapshot';
import { SummaryCard } from './SummaryCard';

const conflict = '订单商品 EUFY-S1-PRO 与当前设备 EUFY-X10-PRO-OMNI 不一致';
const summary: EscalationSummary = {
  product: 'eufy X10', problem: '不吸了', observations: [], hypotheses: [], steps: [],
  reason: { rule_id: 'R1', text: '排障步骤已达上限' },
  emotion: { level: 'calm', strategy: 'normal' }, model_trace: [],
  receipt: { status: 'channel_in_directory', verified_facts: { 'dealer.name': '海科演示授权经销商', authorized: 'true' },
    conflicts: ['订单商品 EUFY-S1-PRO 与当前设备 EUFY-X10-PRO-OMNI 不一致'],
    next_step: '经销商在名录内，人工确认购买凭证后办理' },
};

describe('receipt lookup summary', () => {
  it('shows and copies verified facts, conflicts and next steps', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(<SummaryCard summary={summary} />);
    expect(screen.getByText(/海科演示授权经销商/)).toBeVisible();
    expect(screen.getByText(conflict)).toBeVisible();
    expect(screen.getByText(/下一步：经销商在名录内/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '一键复制' }));
    await screen.findByText('已复制');
    const text = writeText.mock.calls[0]?.[0] ?? ''; 
    expect(text).toContain('海科演示授权经销商');
    expect(text).toContain(conflict);
    expect(text).not.toMatch(/可保|标准质保/);
  });
});
