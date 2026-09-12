import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Composer } from './Composer';
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
  it.each(['select_product', 'step_feedback', 'confirm_receipt'] as const)('restricts %s to card actions while keeping human request available', (pendingKind) => {
    const onSend = vi.fn();
    const onRequestHuman = vi.fn();
    render(<Composer value="旧草稿" onChange={vi.fn()} onSend={onSend} onRequestHuman={onRequestHuman} pendingKind={pendingKind} />);
    expect(screen.getByLabelText('描述你的问题')).toBeDisabled();
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
    expect(screen.getByTestId('image-input')).toBeDisabled();
    fireEvent.submit(screen.getByRole('form', { name: '发送消息' }));
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '请求人工' }));
    expect(onRequestHuman).toHaveBeenCalledOnce();
  });

  it('requires an image for receipt upload and sets purpose=receipt', async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Composer value="购买备注" onChange={vi.fn()} onSend={onSend} pendingKind="upload_receipt" />);
    expect(screen.getByRole('button', { name: '上传凭证' })).toBeDisabled();
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [fileOf(100, 'receipt.png')] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '上传凭证' }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('购买备注', [expect.any(File)], 'receipt'));
    await waitFor(() => expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument());
  });

  it.each([['没有凭证，跳过', 'none'], ['看不清，跳过', 'unreadable'], ['稍后再提供', 'later']] as const)('passes the reason for %s', async (label, reason) => {
    const onSkipReceipt = vi.fn();
    render(<Composer value="" onChange={vi.fn()} pendingKind="upload_receipt" onSkipReceipt={onSkipReceipt} />);
    fireEvent.click(screen.getByRole('button', { name: label }));
    await waitFor(() => expect(onSkipReceipt).toHaveBeenCalledWith(reason));
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
