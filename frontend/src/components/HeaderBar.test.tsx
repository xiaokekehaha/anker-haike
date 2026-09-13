import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HeaderBar } from './HeaderBar';

describe('health indicators', () => {
  it('offers model details without treating missing backup keys as a service outage', () => {
    render(<HeaderBar snapshot={{
      status: 'degraded', lane: 'overseas',
      components: { db: { status: 'down' }, weknora: { status: 'ok' }, models: {
        domestic: { status: 'ok' }, overseas: { status: 'unconfigured' },
      } },
    }} error={null} refreshing={false} checkedAt={new Date()} refresh={vi.fn()} />);
    expect(screen.getByRole('button', { name: /模型/ })).toHaveAttribute('aria-haspopup', 'dialog');
    expect(screen.queryByText('未配置')).not.toBeInTheDocument();
    expect(screen.getByText('不可用')).toBeVisible();
    expect(screen.getByText('可用')).toBeVisible();
    expect(screen.queryByText('已配置')).not.toBeInTheDocument();
  });

  it('shows connection failures for all indicators when the health endpoint is unreachable', () => {
    render(<HeaderBar snapshot={null} error="unreachable" refreshing={false} checkedAt={new Date()} refresh={vi.fn()} />);
    expect(screen.getAllByText('连接异常')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /模型/ })).toBeEnabled();
  });

  it('shows a replay badge only when the backend reports replay mode', () => {
    const snapshot = {
      status: 'ok' as const, lane: 'domestic',
      components: { db: { status: 'ok' as const }, weknora: { status: 'ok' as const }, models: { domestic: { status: 'ok' as const } } },
    };
    const { rerender } = render(<HeaderBar snapshot={snapshot} error={null} refreshing={false} checkedAt={new Date()} refresh={vi.fn()} />);
    expect(screen.queryByText('演示回放')).not.toBeInTheDocument();
    rerender(<HeaderBar snapshot={{ ...snapshot, replay: { status: 'ok', caseId: 'a1_hair_wrap', title: 'A1' } }} error={null} refreshing={false} checkedAt={new Date()} refresh={vi.fn()} />);
    expect(screen.getByText('演示回放')).toBeVisible();
    rerender(<HeaderBar snapshot={{ ...snapshot, replay: { status: 'down', caseId: 'a1_hair_wrap' } }} error={null} refreshing={false} checkedAt={new Date()} refresh={vi.fn()} />);
    expect(screen.getByText('回放不可用')).toBeVisible();
  });
});
