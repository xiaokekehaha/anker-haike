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
    expect(onChange).toHaveBeenCalledWith('');
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
