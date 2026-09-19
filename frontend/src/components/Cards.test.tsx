import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AssistantBubble } from './AssistantBubble';
import { ProductCard } from './ProductCard';
import { SummaryCard, summaryToText } from './SummaryCard';
import { ToolRow } from './ToolRow';

const SUMMARY = {
  product: 'eufy X9 Pro', problem: '冒烟', observations: ['用户补充：有焦味'], hypotheses: [], steps: [{ step_id: 's1', title: '清理滚刷', feedback: 'not_solved' as const }],
  reason: { rule_id: 'R4', text: '检测到安全风险信号' }, emotion: { level: 'anxious' as const, strategy: 'reassure_first' as const },
  receipt: { status: 'not_collected' as const, verified_facts: {}, conflicts: [], next_step: '已转人工' }, model_trace: [],
};

describe('cards', () => {
  it('SummaryCard copies readable text with all five elements', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(<SummaryCard summary={SUMMARY} />);
    fireEvent.click(screen.getByRole('button', { name: '一键复制' }));
    await screen.findByText('已复制');
    const text = writeText.mock.calls[0]?.[0] as string;
    for (const k of ['【产品】eufy X9 Pro', '【问题】冒烟', '【观察】', '【假设】', '【排查记录】清理滚刷（已操作，仍有问题）', '【升级原因】R4', '【凭证】not_collected']) expect(text).toContain(k);
    expect(summaryToText(SUMMARY)).toContain('【凭证核实事实】');
    expect(summaryToText(SUMMARY)).toContain('【凭证待核实差异】');
  });

  it('AssistantBubble sanitizes markdown: script tags are stripped, fallback tier is labelled', () => {
    render(<AssistantBubble item={{ kind: 'assistant_message', message_id: 'm', text: '请先**清理滚刷**<script>alert(1)</script>\n\n- 步骤一', status: 'completed', model_tier: 'fallback', replaces: null }} />);
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText('清理滚刷')).toBeVisible();
    expect(screen.getByText('简化回复')).toBeVisible();
    expect(screen.getByRole('listitem')).toHaveTextContent('步骤一');
  });

  it('ProductCard marks out-of-scope candidates and disables after selection', () => {
    const onSelect = vi.fn();
    const item = { kind: 'product_card' as const, card_id: 'c', version: 1, selected_sku: null, candidates: [
      { sku: 'RV', name: 'eufy S1 Pro 扫地机器人', category: 'robot_vacuum', image: null, in_scope: true },
      { sku: 'BP', name: 'eufy S1 Pro 吸奶器', category: 'breast_pump', image: null, in_scope: false },
    ] };
    const { rerender } = render(<ProductCard item={item} active onSelect={onSelect} />);
    expect(screen.getByText('本期不支持')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /扫地机器人/ }));
    expect(onSelect).toHaveBeenCalledWith('RV');
    rerender(<ProductCard item={{ ...item, selected_sku: 'RV' }} active={false} onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: /扫地机器人/ })).toBeDisabled();
    expect(screen.getByText('已选择')).toBeVisible();
  });

  it('ProductCard offers an unknown exit only on model cards and locks after choosing it', () => {
    const onSelect = vi.fn();
    const item = { kind: 'product_card' as const, card_id: 'c', version: 1, selected_sku: null, allow_unknown: true, note: '不同型号的排查方法不同', candidates: [
      { sku: 'X10', name: 'eufy X10 Pro Omni', category: 'robot_vacuum', image: null, in_scope: true },
    ] };
    const { rerender } = render(<ProductCard item={item} active onSelect={onSelect} />);
    expect(screen.getByText('不同型号的排查方法不同')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /其他型号/ }));
    expect(onSelect).toHaveBeenCalledWith(null);
    rerender(<ProductCard item={{ ...item, selected_unknown: true }} active onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: /其他型号/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /X10/ })).toBeDisabled();
    expect(screen.getByText('已选择')).toBeVisible();
    rerender(<ProductCard item={{ ...item, allow_unknown: false }} active onSelect={onSelect} />);
    expect(screen.queryByRole('button', { name: /其他型号/ })).toBeNull();
  });

  it('ToolRow shows failed state text', () => {
    render(<ToolRow item={{ kind: 'tool', tool_id: 't', name: 'knowledge.search', status: 'failed', summary: '知识库暂不可用，按标准排障流程' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('检索知识库');
    expect(screen.getByText('知识库暂不可用，按标准排障流程')).toBeVisible();
  });
});
