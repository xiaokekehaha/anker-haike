import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SessionSwitcher, optionLabel } from './SessionSwitcher';
import type { RecentSession } from '../state/recentSessions';

const now = new Date().toISOString();
const recent: RecentSession[] = [
  { id: 'a', created_at: now, updated_at: now, title: '扫地机不吸尘', stage: 'guide' },
  { id: 'b', created_at: now, updated_at: now, title: null, stage: null },
];

describe('SessionSwitcher', () => {
  it('lists recent sessions with the current one selected and switches on change', () => {
    const onSwitch = vi.fn();
    render(<SessionSwitcher currentId="a" recent={recent} busy={false} onNew={vi.fn()} onSwitch={onSwitch} />);
    const select = screen.getByLabelText('切换会话') as HTMLSelectElement;
    expect(select.value).toBe('a');
    expect(screen.getByText('（当前）扫地机不吸尘 · 分步排障')).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'b' } });
    expect(onSwitch).toHaveBeenCalledWith('b');
  });

  it('disables 新建会话 on a blank session and hides the list when nothing is recorded', () => {
    render(<SessionSwitcher currentId={null} recent={[]} busy={false} onNew={vi.fn()} onSwitch={vi.fn()} />);
    expect(screen.getByRole('button', { name: '新建会话' })).toBeDisabled();
    expect(screen.queryByLabelText('切换会话')).toBeNull();
  });

  it('keeps 新建会话 clickable while a run is in progress so the user can interrupt it', () => {
    const onNew = vi.fn();
    render(<SessionSwitcher currentId="a" recent={recent} busy onNew={onNew} onSwitch={vi.fn()} />);
    expect(screen.getByLabelText('切换会话')).toBeDisabled();
    const button = screen.getByRole('button', { name: '新建会话' });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(onNew).toHaveBeenCalledTimes(1);
  });

  it('shows a freshly created session even before it reaches the recent list', () => {
    render(<SessionSwitcher currentId="fresh" recent={recent} busy={false} onNew={vi.fn()} onSwitch={vi.fn()} />);
    expect((screen.getByLabelText('切换会话') as HTMLSelectElement).value).toBe('fresh');
    expect(optionLabel(recent[1]!, false)).toMatch(/^新会话 · /);
  });
});
