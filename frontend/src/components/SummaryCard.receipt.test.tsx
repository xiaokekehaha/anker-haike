import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EscalationSummary } from '../types/snapshot';
import { SummaryCard } from './SummaryCard';

const conflict = '订单 Anker002 的商品与当前设备 T8D04 不一致';
const summary: EscalationSummary = {
  product: 'eufy X10', problem: '不吸了', observations: [], hypotheses: [], steps: [],
  reason: { rule_id: 'R1', text: '排障步骤已达上限' },
  emotion: { level: 'calm', strategy: 'normal' }, model_trace: [],
  receipt: { status: 'dealer_authorized', verified_facts: { dealer: 'Aeroflow Breastpumps', country: 'US' },
    conflicts: ['订单 Anker002 的商品与当前设备 T8D04 不一致'],
    next_step: '购买商家在授权经销商名录内，按购买日起 12 个月判断质保' },
};

describe('receipt lookup summary', () => {
  it('shows and copies verified facts, conflicts and next steps', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(<SummaryCard summary={summary} />);
    expect(screen.getByText(/Aeroflow Breastpumps/)).toBeVisible();
    expect(screen.getByText(conflict)).toBeVisible();
    expect(screen.getByText(/下一步：购买商家在授权经销商名录内/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '一键复制' }));
    await screen.findByText('已复制');
    const text = writeText.mock.calls[0]?.[0] ?? ''; 
    expect(text).toContain('Aeroflow Breastpumps');
    expect(text).toContain(conflict);
    expect(text).not.toMatch(/可保|标准质保/);
  });
});
