import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

vi.mock('./state/useHealth', () => ({
  useHealth: () => ({ snapshot: null, error: null, refreshing: false, checkedAt: null, refresh: vi.fn() }),
}));

describe('customer-service shell', () => {
  beforeEach(() => render(<App />));

  it('is not tied to a single product category', () => {
    expect(screen.queryByText(/扫地机器人 · 售后支持/)).not.toBeInTheDocument();
    for (const label of ['扫地机器人', '吸奶器', '耳机与音箱', '充电与移动电源']) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeVisible();
    }
  });

  it('shows the five-stage progress bar in idle state', () => {
    const steps = screen.getAllByRole('listitem', { name: '' }).filter((li) => li.closest('[aria-label="处理进度"]'));
    expect(steps).toHaveLength(5);
    expect(screen.getByText('确认产品')).toBeVisible();
  });

  it('fills the composer from a starter prompt but keeps sending disabled until the backend is wired', () => {
    fireEvent.click(screen.getByText('不知道怎么说？看看示例'));
    fireEvent.click(screen.getByRole('button', { name: /S1 Pro 不吸了/ }));
    expect(screen.getByLabelText('描述你的问题')).toHaveValue('我的 S1 Pro 不吸了，明天家里要来客人，急！');
    expect(screen.getByLabelText('描述你的问题')).toHaveFocus();
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
  });
});
