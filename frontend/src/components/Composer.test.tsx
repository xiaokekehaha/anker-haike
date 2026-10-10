import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Composer, REDIAGNOSE_HINT } from './Composer';
import { UserBubble } from './UserBubble';
import { checkImage, MAX_IMAGE_BYTES } from '../lib/image';

function fileOf(size: number, name = 'a.png', type = 'image/png'): File {
  const f = new File([new Uint8Array(8)], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

describe('Composer image attachments (票 29)', () => {
  it('rejects a 6 MB image inline and never sends it', async () => {
    const onSend = vi.fn();
    render(<Composer value="看下这张图" onChange={() => {}} onSend={onSend} />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(6 * 1024 * 1024, 'big.png')] } });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('超过 5 MB');
    expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument();
    fireEvent.submit(screen.getByRole('form', { name: '发送消息' }));
    expect(onSend).toHaveBeenCalledWith('看下这张图', [], 'fault');
  });

  it('rejects non-image files with a type hint', async () => {
    render(<Composer value="" onChange={() => {}} />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(100, 'a.pdf', 'application/pdf')] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('不支持的文件类型');
  });

  it('accepts a small image, shows it as pending and sends it with the text', async () => {
    const onSend = vi.fn();
    const onChange = vi.fn();
    render(<Composer value="滚刷这样正常吗" onChange={onChange} onSend={onSend} />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(200 * 1024, 'brush.jpg', 'image/jpeg')] } });
    await waitFor(() => expect(screen.getByLabelText('待发送图片')).toBeInTheDocument());
    expect(screen.getByLabelText('移除图片 1')).toBeInTheDocument();
    fireEvent.submit(screen.getByRole('form', { name: '发送消息' }));
    expect(onSend).toHaveBeenCalledTimes(1);
    const [text, files, purpose] = onSend.mock.calls[0] as [string, File[], string];
    expect(text).toBe('滚刷这样正常吗');
    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe('brush.jpg');
    expect(purpose).toBe('fault');
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(''));
  });

  it('caps the number of images per message', async () => {
    render(<Composer value="" onChange={() => {}} maxImages={1} />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(10, '1.png'), fileOf(10, '2.png')] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('最多附带 1 张');
  });
});

describe('UserBubble thumbnails', () => {
  it('renders one thumbnail per image ref from the session image endpoint', () => {
    render(<UserBubble sessionId="s1" text="不吸了" images={[{ image_id: 'img-a', purpose: 'fault' }, { image_id: 'img-b', purpose: 'receipt' }]} />);
    const imgs = screen.getAllByRole('img');
    expect(imgs).toHaveLength(2);
    expect(imgs[0]).toHaveAttribute('src', '/sessions/s1/images/img-a');
    expect(imgs[0]).toHaveAttribute('alt', '故障图片 1');
    expect(imgs[1]).toHaveAttribute('alt', '购买凭证 2');
    expect(screen.getByText('不吸了')).toBeVisible();
  });
});

describe('checkImage', () => {
  it('flags size and type', () => {
    expect(checkImage({ size: MAX_IMAGE_BYTES + 1, type: 'image/png' })).toMatchObject({ ok: false, code: 'too_large' });
    expect(checkImage({ size: 10, type: 'text/plain' })).toMatchObject({ ok: false, code: 'unsupported_type' });
    expect(checkImage({ size: 10, type: 'image/webp' })).toEqual({ ok: true });
  });
});

describe('pending input modes', () => {
  it('lets the user supplement or correct while a step card waits (rediagnose, ticket 37)', async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    const onChange = vi.fn();
    render(<Composer value="其实还有异响" onChange={onChange} onSend={onSend} pendingKind="step_feedback" />);
    expect(screen.getByText(REDIAGNOSE_HINT)).toBeVisible();
    expect(screen.getByLabelText('补充新情况或纠正')).toBeEnabled();
    expect(screen.getByTestId('image-input')).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('其实还有异响', [], 'fault'));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(''));
  });

  // CM 交接契约 §7 / 验收 A35：四种 pending 下都允许纯文字追问，卡片操作另走动作接口。
  it.each(['select_product', 'confirm_receipt'] as const)('keeps plain text and photos available while a %s card waits', async (pendingKind) => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="顺便问一下保修多久" onChange={vi.fn()} onSend={onSend} pendingKind={pendingKind} />);
    expect(screen.getByLabelText('描述你的问题')).toBeEnabled();
    expect(screen.getByTestId('image-input')).toBeEnabled();
    expect(screen.getByRole('button', { name: '发送' })).toBeEnabled();
    fireEvent.submit(screen.getByRole('form', { name: '发送消息' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('顺便问一下保修多久', [], 'fault'));
  });

  it('allows a text-only question while waiting for the receipt, and sends attachments as purpose=receipt', async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="购买备注" onChange={vi.fn()} onSend={onSend} pendingKind="upload_receipt" />);
    expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled();
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(100, 'receipt.png')] } });
    await waitFor(() => expect(screen.getByLabelText('待发送图片')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('购买备注', [expect.any(File)], 'receipt'));
    await waitFor(() => expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument());
  });

  it('sends the note alone when there is no receipt image yet', async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="发票在公司，明天补" onChange={vi.fn()} onSend={onSend} pendingKind="upload_receipt" />);
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('发票在公司，明天补', [], 'receipt'));
  });

  it('offers a single skip option while waiting for the receipt', async () => {
    const onSkipReceipt = vi.fn();
    render(<Composer value="" onChange={vi.fn()} pendingKind="upload_receipt" onSkipReceipt={onSkipReceipt} />);
    expect(screen.queryByRole('button', { name: '请求人工' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '暂时没有凭证，跳过' }));
    await waitFor(() => expect(onSkipReceipt).toHaveBeenCalledOnce());
  });

  it('preserves attachments and draft when the server rejects the upload', async () => {
    const onSend = vi.fn().mockResolvedValue(false);
    const onChange = vi.fn();
    render(<Composer value="购买备注" onChange={onChange} onSend={onSend} pendingKind="upload_receipt" />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(100)] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    expect(screen.getByLabelText('待发送图片')).toBeVisible();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('removes fault attachments on entering receipt upload instead of changing their purpose', async () => {
    const props = { value: '', onChange: vi.fn(), onSend: vi.fn() };
    const { rerender } = render(<Composer {...props} />);
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(100, 'fault.png')] } });
    await screen.findByLabelText('待发送图片');
    rerender(<Composer {...props} pendingKind="upload_receipt" purpose="receipt" />);
    expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上传凭证' })).toBeDisabled();
  });
});

function stubTouchPrimary(matches: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('pointer: coarse') ? matches : false,
    media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  }));
}

describe('Composer keyboard sending', () => {
  it('sends on Enter and keeps Shift+Enter as a newline on desktop', async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="一边没声音" onChange={vi.fn()} onSend={onSend} />);
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('一边没声音', [], 'fault'));
  });

  it('ignores the Enter that confirms an IME candidate', () => {
    const onSend = vi.fn();
    render(<Composer value="一边没声音" onChange={vi.fn()} onSend={onSend} />);
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
  });

  it('does not send an empty draft on Enter', () => {
    const onSend = vi.fn();
    render(<Composer value="   " onChange={vi.fn()} onSend={onSend} />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('leaves Enter as a newline on touch devices but still accepts Cmd/Ctrl+Enter', async () => {
    stubTouchPrimary(true);
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="一边没声音" onChange={vi.fn()} onSend={onSend} />);
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByText(/Enter 发送/)).not.toBeInTheDocument();
    fireEvent.keyDown(input, { key: 'Enter', metaKey: true });
    await waitFor(() => expect(onSend).toHaveBeenCalledOnce());
  });

  it('shows the desktop keyboard hint', () => {
    stubTouchPrimary(false);
    render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
    expect(screen.getByText(/Enter 发送，Shift\+Enter 换行/)).toBeInTheDocument();
  });
});

describe('Composer clipboard images', () => {
  it('attaches an image pasted into the textarea', async () => {
    render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
    fireEvent.paste(screen.getByRole('textbox'), { clipboardData: { files: [fileOf(120 * 1024, 'shot.png')], items: [] } });
    await screen.findByLabelText('待发送图片');
    expect(screen.getByLabelText('移除图片 1')).toBeInTheDocument();
  });

  it('falls back to clipboard items when files is empty', async () => {
    const file = fileOf(120 * 1024, 'shot.png');
    render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
    fireEvent.paste(screen.getByRole('textbox'), {
      clipboardData: { files: [], items: [{ kind: 'file', type: 'image/png', getAsFile: () => file }] },
    });
    await screen.findByLabelText('待发送图片');
  });

  it('leaves plain text pastes to the browser', () => {
    render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
    fireEvent.paste(screen.getByRole('textbox'), { clipboardData: { files: [], items: [{ kind: 'string', type: 'text/plain', getAsFile: () => null }] } });
    expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument();
  });

  it('reports oversized pasted images inline', async () => {
    render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
    fireEvent.paste(screen.getByRole('textbox'), { clipboardData: { files: [fileOf(6 * 1024 * 1024, 'big.png')], items: [] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('超过 5 MB');
  });
});
