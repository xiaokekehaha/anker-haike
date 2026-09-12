import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Composer } from './Composer';
import { prepareImage } from '../lib/image';

vi.mock('../lib/image', async importOriginal => ({ ...await importOriginal<typeof import('../lib/image')>(), prepareImage: vi.fn() }));
const prepare = vi.mocked(prepareImage);
const file = new File(['image'], 'receipt.png', { type: 'image/png' });
const createURL = vi.fn(() => 'blob:receipt');
const revokeURL = vi.fn();
let oldCreate: typeof URL.createObjectURL;
let oldRevoke: typeof URL.revokeObjectURL;
beforeEach(() => {
  prepare.mockReset(); createURL.mockClear(); revokeURL.mockClear();
  oldCreate = URL.createObjectURL; oldRevoke = URL.revokeObjectURL;
  URL.createObjectURL = createURL; URL.revokeObjectURL = revokeURL;
});
afterEach(() => { URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke; });

it('discards a late compression result after the input purpose changes', async () => {
  let finish!: (result: { file: File }) => void;
  prepare.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const props = { value: '', onChange: vi.fn(), onSend: vi.fn() };
  const { rerender } = render(<Composer {...props} />);
  fireEvent.change(screen.getByTestId('image-input'), { target: { files: [file] } });
  rerender(<Composer {...props} pendingKind="upload_receipt" purpose="receipt" />);
  await act(async () => finish({ file }));
  expect(screen.queryByLabelText('待发送图片')).not.toBeInTheDocument();
  expect(createURL).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '上传凭证' })).toBeDisabled();
});

it('releases preview URLs when the composer unmounts', async () => {
  prepare.mockResolvedValue({ file });
  const { unmount } = render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} />);
  fireEvent.change(screen.getByTestId('image-input'), { target: { files: [file] } });
  await screen.findByLabelText('待发送图片');
  unmount();
  expect(revokeURL).toHaveBeenCalledExactlyOnceWith('blob:receipt');
});

it('keeps preview and note after a rejected send promise and blocks double submission', async () => {
  prepare.mockResolvedValue({ file });
  let reject!: (error: Error) => void;
  const onSend = vi.fn(() => new Promise<void>((_, no) => { reject = no; }));
  const onChange = vi.fn();
  render(<Composer value="纸质发票" onChange={onChange} onSend={onSend} pendingKind="upload_receipt" />);
  fireEvent.change(screen.getByTestId('image-input'), { target: { files: [file] } });
  await waitFor(() => expect(screen.getByRole('button', { name: '上传凭证' })).toBeEnabled());
  const form = screen.getByRole('form', { name: '上传购买凭证' });
  fireEvent.submit(form); fireEvent.submit(form);
  expect(onSend).toHaveBeenCalledOnce();
  await act(async () => reject(new Error('offline')));
  expect(screen.getByRole('alert')).toHaveTextContent('附件与备注已保留');
  expect(screen.getByLabelText('待发送图片')).toBeVisible();
  expect(onChange).not.toHaveBeenCalled();
  expect(revokeURL).not.toHaveBeenCalled();
});
