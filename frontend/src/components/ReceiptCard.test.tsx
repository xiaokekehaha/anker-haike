import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReceiptCard } from './ReceiptCard';
import type { ReceiptCardItem } from '../types/snapshot';

function card(patch: Partial<ReceiptCardItem> = {}): ReceiptCardItem {
  return { kind: 'receipt_card', card_id: 'c', version: 4,
    fields: { order_no: '00123', channel: '示例店', purchase_date: '2026-09-01', amount: '￥999' },
    confidence: { order_no: 0.5, channel: 0.95 }, unreadable: [], confirmed_fields: null, skipped_reason: null, ...patch };
}

describe('receipt field confirmation', () => {
  it('marks uncertain fields and submits only fields actually changed', () => {
    const onConfirm = vi.fn();
    render(<ReceiptCard item={card()} active onConfirm={onConfirm} onSkip={vi.fn()} />);
    expect(screen.getByLabelText('订单号').closest('[data-low]')).not.toBeNull();
    expect(screen.getByLabelText('购买渠道').closest('[data-low]')).toBeNull();
    fireEvent.change(screen.getByLabelText('订单号'), { target: { value: '00999' } });
    fireEvent.click(screen.getByRole('button', { name: /^确认$/ }));
    expect(onConfirm).toHaveBeenCalledWith({ ...card().fields, order_no: '00999' }, ['order_no']);
  });

  it('does not count a value changed back to the OCR original as edited', () => {
    const onConfirm = vi.fn();
    render(<ReceiptCard item={card()} active onConfirm={onConfirm} onSkip={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('订单号'), { target: { value: '999' } });
    fireEvent.change(screen.getByLabelText('订单号'), { target: { value: '00123' } });
    fireEvent.click(screen.getByRole('button', { name: /^确认$/ }));
    expect(onConfirm).toHaveBeenCalledWith(card().fields, []);
  });

  it('allows manual entry and skipping when all fields are unreadable', () => {
    const onConfirm = vi.fn();
    const onSkip = vi.fn();
    render(<ReceiptCard item={card({ fields: {}, unreadable: ['order_no', 'channel', 'purchase_date', 'amount'] })} active onConfirm={onConfirm} onSkip={onSkip} />);
    expect(screen.getAllByText('未识别')).toHaveLength(4);
    fireEvent.change(screen.getByLabelText('购买渠道'), { target: { value: '示例专卖店' } });
    fireEvent.click(screen.getByRole('button', { name: /^确认$/ }));
    expect(onConfirm).toHaveBeenCalledWith({ channel: '示例专卖店' }, ['channel']);
    fireEvent.click(screen.getByRole('button', { name: '看不清，跳过' }));
    expect(onSkip).toHaveBeenCalledWith('unreadable');
  });

  it('preserves edits on identical replay but replaces them when authoritative fields change', () => {
    const props = { active: true, onConfirm: vi.fn(), onSkip: vi.fn() };
    const { rerender } = render(<ReceiptCard item={card()} {...props} />);
    fireEvent.change(screen.getByLabelText('订单号'), { target: { value: 'draft' } });
    rerender(<ReceiptCard item={card()} {...props} />);
    expect(screen.getByLabelText('订单号')).toHaveValue('draft');
    rerender(<ReceiptCard item={card({ version: 8, fields: { order_no: 'server' } })} {...props} />);
    expect(screen.getByLabelText('订单号')).toHaveValue('server');
  });

  it('shows confirmed server values on restore and disables historical cards', () => {
    const props = { onConfirm: vi.fn(), onSkip: vi.fn() };
    const { rerender } = render(<ReceiptCard item={card()} active {...props} />);
    rerender(<ReceiptCard item={card({ confirmed_fields: { order_no: 'server-confirmed', channel: '新店铺' } })} active={false} {...props} />);
    expect(screen.getByLabelText('订单号')).toHaveValue('server-confirmed');
    expect(screen.getByLabelText('订单号')).toBeDisabled();
    expect(screen.getByText('已确认')).toBeVisible();
    expect(screen.queryByRole('button', { name: /^确认$/ })).not.toBeInTheDocument();
  });
});
