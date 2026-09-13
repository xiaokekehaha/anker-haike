import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ModelDialog } from './ModelDialog';
import { HeaderBar } from './HeaderBar';
import type { ModelList, ModelStatus } from '../api/models';

const model = (alias: string, overrides: Partial<ModelStatus> = {}): ModelStatus => ({
  alias, model_id: alias, provider: 'deepseek', current_lane: true, configured: true,
  status: 'unchecked', detail: null, latency_ms: null, checked_at: null, expires_at: null, ...overrides,
});
const deepseek = model('deepseek');
const glm = model('glm');
const missing = model('qwen', { configured: false, status: 'unconfigured', detail: '缺少密钥' });
const other = model('sonnet', { current_lane: false });
const list: ModelList = { lane: 'domestic', models: [deepseek, glm, missing, other], probe_enabled: true, disabled_reason: null };
const connected = (item: ModelStatus): ModelStatus => ({ ...item, status: 'connected', latency_ms: 820,
  checked_at: new Date().toISOString(), expires_at: new Date(Date.now() + 300_000).toISOString() });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true,
    value: function (this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true,
    value: function (this: HTMLDialogElement) { this.removeAttribute('open'); } });
});

describe('model connection dialog', () => {
  it('opens from the header, fetches only the list, and closes', async () => {
    const fetch = vi.fn().mockResolvedValue(json(list));
    vi.stubGlobal('fetch', fetch);
    render(<HeaderBar snapshot={null} error={null} refreshing={false} checkedAt={null} refresh={vi.fn()} />);
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /模型/ }));
    expect(await screen.findByRole('dialog')).toBeVisible();
    expect(await screen.findByText('缺少密钥')).toBeVisible();
    expect(screen.getByRole('button', { name: '检测 qwen' })).toBeDisabled();
    expect(screen.getByText('sonnet')).not.toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[0]).toBe('/models/status');
    fireEvent.click(screen.getByRole('button', { name: '关闭模型列表' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /模型/ })).toHaveFocus();
  });

  it('batches current configured models and shows each result as it arrives', async () => {
    let finishGlm: (response: Response) => void = () => {};
    const fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/models/status') return Promise.resolve(json(list));
      if (url === '/models/deepseek/probe') return Promise.resolve(json(connected(deepseek)));
      if (url === '/models/glm/probe') return new Promise<Response>((resolve) => { finishGlm = resolve; });
      throw new Error(`unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetch);
    render(<ModelDialog onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '检测已配置模型' }));
    expect(await screen.findByText('已连通')).toBeVisible();
    expect(within(screen.getByRole('listitem', { name: 'glm 模型' })).getByText('检测中')).toBeVisible();
    expect(screen.getByRole('button', { name: '正在检测…' })).toBeDisabled();
    await act(async () => finishGlm(json({ ...connected(glm), status: 'failed', detail: '请求超时' })));
    expect(await screen.findByText('请求超时')).toBeVisible();
    expect(screen.getByRole('button', { name: '检测已配置模型' })).toBeEnabled();
    const posts = fetch.mock.calls.filter((call) => call[1]?.method === 'POST').map((call) => call[0]);
    expect(posts).toEqual(['/models/deepseek/probe', '/models/glm/probe']);
  });

  it('supports a single retest and clears an old green result on request failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json({ ...list, models: [connected(deepseek)] }))
      .mockResolvedValueOnce(json({}, 429))
      .mockResolvedValueOnce(json(connected(deepseek))));
    render(<ModelDialog onClose={vi.fn()} />);
    expect(await screen.findByText('已连通')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '检测 deepseek' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('检测请求较多');
    expect(screen.queryByText('已连通')).not.toBeInTheDocument();
    expect(screen.getByText('未检测')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '检测 deepseek' }));
    expect(await screen.findByText('已连通')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('can inspect other models and respects disabled environments', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ...list, probe_enabled: false, disabled_reason: '演示回放模式不发起真实模型检测' }));
    vi.stubGlobal('fetch', fetch);
    render(<ModelDialog onClose={vi.fn()} />);
    expect(await screen.findByText('演示回放模式不发起真实模型检测')).toBeVisible();
    fireEvent.click(screen.getByText('其他模型'));
    expect(screen.getByText('sonnet')).toBeVisible();
    expect(screen.getByRole('button', { name: '检测 sonnet' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '检测已配置模型' })).toBeDisabled();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('reports list failures and permits retry without probing', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce(json(list));
    vi.stubGlobal('fetch', fetch);
    render(<ModelDialog onClose={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法获取模型列表');
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
    expect(await screen.findByText('缺少密钥')).toBeVisible();
    expect(fetch.mock.calls.every((call) => call[0] === '/models/status')).toBe(true);
  });

  it('expires results while the dialog remains open, without automatic paid calls', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValue(json({ ...list, models: [{ ...connected(deepseek), expires_at: new Date(Date.now() + 1_000).toISOString() }] }));
    vi.stubGlobal('fetch', fetch);
    await act(async () => { render(<ModelDialog onClose={vi.fn()} />); });
    expect(screen.getByText('已连通')).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(1_100); });
    expect(screen.getByText('未检测')).toBeVisible();
    expect(screen.getByText('上次检测已过期，请重新检测')).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('reopens an ongoing probe by polling its result without starting another call', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn()
      .mockResolvedValueOnce(json({ ...list, models: [model('deepseek', { status: 'checking' })] }))
      .mockResolvedValueOnce(json({ ...list, models: [connected(deepseek)] }));
    vi.stubGlobal('fetch', fetch);
    await act(async () => { render(<ModelDialog onClose={vi.fn()} />); });
    expect(screen.getByText('检测中')).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(1_100); });
    expect(screen.getByText('已连通')).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls.every((call) => call[0] === '/models/status')).toBe(true);
  });

  it('stops queued probes when closed and aborts requests', async () => {
    const fetch = vi.fn().mockImplementation((url: string) => url === '/models/status'
      ? Promise.resolve(json({ ...list, models: [deepseek, glm, model('third')] }))
      : new Promise<Response>(() => {}));
    vi.stubGlobal('fetch', fetch);
    const { unmount } = render(<ModelDialog onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '检测已配置模型' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    unmount();
    for (const call of fetch.mock.calls.slice(1)) expect(call[1].signal.aborted).toBe(true);
    expect(fetch.mock.calls.some((call) => call[0] === '/models/third/probe')).toBe(false);
  });

  it('ignores the cancelled StrictMode list request', async () => {
    const fetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => new Promise<Response>((resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      queueMicrotask(() => resolve(json(list)));
    }));
    vi.stubGlobal('fetch', fetch);
    render(<StrictMode><ModelDialog onClose={vi.fn()} /></StrictMode>);
    expect(await screen.findByText('缺少密钥')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
