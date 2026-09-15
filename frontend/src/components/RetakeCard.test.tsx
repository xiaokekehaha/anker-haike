import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RetakeCard } from './RetakeCard';
import type { RetakeCardItem } from '../types/snapshot';

const item = (over: Partial<RetakeCardItem> = {}): RetakeCardItem => ({
  kind: 'retake_card', card_id: 'c1', version: 1, at: '2026-09-15T00:00:00Z', seq: 1,
  reasons: ['too_dark'], guidance: ['请在光线充足处拍摄。'], skipped: false, ...over,
} as RetakeCardItem);

describe('RetakeCard', () => {
  it('把机器码翻成人话，不把 too_dark 摆给用户', () => {
    render(<RetakeCard item={item()} active onSkip={vi.fn()} />);
    expect(screen.getByText('光线偏暗')).toBeInTheDocument();
    expect(screen.queryByText(/too_dark/)).toBeNull();
    expect(screen.getByText('请在光线充足处拍摄。')).toBeInTheDocument();
  });

  it('遇到没见过的码时原样显示，不吞掉信息', () => {
    render(<RetakeCard item={item({ reasons: ['brand_new_reason'] })} active onSkip={vi.fn()} />);
    expect(screen.getByText('brand_new_reason')).toBeInTheDocument();
  });

  it('已跳过时按钮禁用并改文案', () => {
    render(<RetakeCard item={item({ skipped: true })} active onSkip={vi.fn()} />);
    expect(screen.getByRole('button', { name: '已跳过补拍' })).toBeDisabled();
  });
});
