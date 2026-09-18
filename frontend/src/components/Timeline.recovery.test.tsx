import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { initialState, type SessionState } from '../state/types';
import { Timeline } from './Timeline';

const state: SessionState = { ...initialState, id: 'session', activeIssueId: 'issue', stage: 'guide' };

describe('当前问题的排查调整入口', () => {
  it('允许改选、暂停和继续，发送明确意图', () => {
    const send = vi.fn();
    render(<Timeline state={state} onAction={vi.fn()} onDiagnosticMessage={send} />);
    const controls = within(screen.getByRole('navigation', { name: '调整排查' }));
    for (const name of ['重新选择现象', '暂停排查', '继续排查']) {
      fireEvent.click(controls.getByRole('button', { name }));
      expect(send).toHaveBeenLastCalledWith(name);
    }
  });

  it('摘要结束后仍可改选或继续，不必新建问题', () => {
    render(<Timeline state={{ ...state, stage: 'escalate' }} onAction={vi.fn()} onDiagnosticMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: '重新选择现象' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '继续排查' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '暂停排查' })).not.toBeInTheDocument();
  });

  it.each(['streaming', 'tool_running', 'recovering'] as const)('处理期间 %s 不重复发送', ui => {
    const send = vi.fn();
    render(<Timeline state={{ ...state, ui }} onAction={vi.fn()} onDiagnosticMessage={send} />);
    const button = screen.getByRole('button', { name: '重新选择现象' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(send).not.toHaveBeenCalled();
  });

  it('没有当前问题时不显示排查操作', () => {
    render(<Timeline state={initialState} onAction={vi.fn()} onDiagnosticMessage={vi.fn()} />);
    expect(screen.queryByRole('navigation', { name: '调整排查' })).not.toBeInTheDocument();
  });
});
