import { useEffect, useId, useRef, useState } from 'react';
import type { Ref } from 'react';
import { prepareImage } from '../lib/image';
import type { ImagePurpose } from '../lib/image';
import type { PendingInput } from '../types/snapshot';
import styles from './Composer.module.css';

export type Attachment = { id: string; file: File; previewUrl: string | null };
type SkipReason = 'none' | 'unreadable' | 'later';
type Props = {
  value: string;
  onChange: (v: string) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  offline?: boolean;
  /** 返回 false 表示未被服务端接收，保留附件与草稿。 */
  onSend?: (text: string, files: File[], purpose: ImagePurpose) => void | boolean | Promise<void | boolean>;
  onRequestHuman?: () => void;
  onSkipReceipt?: (reason: SkipReason) => void | Promise<void>;
  pendingKind?: PendingInput['kind'] | null;
  purpose?: ImagePurpose;
  maxImages?: number;
  busy?: boolean;
  onCancel?: () => void;
};

const WAITING_HINT = {
  select_product: '请先在上方卡片选择产品。',
  step_feedback: '请先在步骤卡反馈操作结果，补充说明可填写在卡片内。',
  confirm_receipt: '请在上方核对订单号、购买渠道等信息，确认或跳过。',
};
let seq = 0;
function makePreview(file: File): string | null {
  try { return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null; }
  catch { return null; }
}
function release(items: Attachment[]) {
  for (const item of items) if (item.previewUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(item.previewUrl);
}

export function Composer({ value, onChange, offline, inputRef, onSend, onRequestHuman, onSkipReceipt, pendingKind = null, purpose = 'fault', maxImages = 3, busy: runBusy = false, onCancel }: Props) {
  const inputId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const attachmentsRef = useRef<Attachment[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const processingRef = useRef(false);
  const submittingRef = useRef(false);
  const generation = useRef(0);
  const receipt = pendingKind === 'upload_receipt';
  const cardOnly = pendingKind !== null && !receipt;
  const busy = processing || submitting;
  const inputBlocked = !!offline || runBusy || cardOnly || busy;
  const hasContent = receipt ? attachments.length > 0 : value.trim().length > 0 || attachments.length > 0;
  const canSend = !inputBlocked && !!onSend && hasContent;

  useEffect(() => {
    generation.current++;
    setAttachments([]);
    setImageError(null);
    setProcessing(false);
    setSubmitting(false);
    processingRef.current = false;
    submittingRef.current = false;
    return () => {
      generation.current++;
      release(attachmentsRef.current);
      attachmentsRef.current = [];
    };
  }, [purpose, pendingKind]);

  function updateAttachments(items: Attachment[]) {
    attachmentsRef.current = items;
    setAttachments(items);
  }

  async function addFiles(list: FileList | File[]) {
    if (inputBlocked || processingRef.current) return;
    setImageError(null);
    const files = Array.from(list);
    if (!files.length) return;
    if (attachmentsRef.current.length + files.length > maxImages) {
      setImageError(`一次最多附带 ${maxImages} 张图片。`);
      return;
    }
    const batch = generation.current;
    processingRef.current = true;
    setProcessing(true);
    const accepted: Attachment[] = [];
    const errors: string[] = [];
    try {
      for (const file of files) {
        const result = await prepareImage(file);
        if (batch !== generation.current) { release(accepted); return; }
        if ('error' in result) errors.push(`${file.name}：${result.error}`);
        else accepted.push({ id: `img-${++seq}`, file: result.file, previewUrl: makePreview(result.file) });
      }
      updateAttachments([...attachmentsRef.current, ...accepted]);
      if (errors.length) setImageError(errors.join('；'));
    } catch {
      release(accepted);
      if (batch === generation.current) setImageError('图片处理失败，请重新选择。');
    } finally {
      if (batch === generation.current) { processingRef.current = false; setProcessing(false); }
    }
  }

  function remove(id: string) {
    release(attachmentsRef.current.filter(item => item.id === id));
    updateAttachments(attachmentsRef.current.filter(item => item.id !== id));
  }

  async function submit() {
    if (!canSend || submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    const batch = generation.current;
    try {
      const sent = await onSend?.(value.trim(), attachmentsRef.current.map(item => item.file), receipt ? 'receipt' : purpose);
      if (batch !== generation.current || sent === false) return;
      release(attachmentsRef.current);
      updateAttachments([]);
      setImageError(null);
      onChange('');
    } catch {
      if (batch === generation.current) setImageError('发送失败，附件与备注已保留，请重试。');
    } finally {
      if (batch === generation.current) { submittingRef.current = false; setSubmitting(false); }
    }
  }

  async function skip(reason: SkipReason) {
    if (inputBlocked || submittingRef.current || !onSkipReceipt) return;
    submittingRef.current = true;
    setSubmitting(true);
    const batch = generation.current;
    try { await onSkipReceipt(reason); }
    catch { if (batch === generation.current) setImageError('暂时无法跳过，请重试。'); }
    finally { if (batch === generation.current) { submittingRef.current = false; setSubmitting(false); } }
  }

  const hint = offline ? '可以先填写问题；对话服务暂未接通，目前无法发送。'
    : cardOnly ? WAITING_HINT[pendingKind]
    : receipt ? '请上传订单截图、发票或收据，可附带备注；单张 5 MB 内。也可以跳过，由人工协助核实。'
    : '支持文字与图片（单张 5 MB 内，会自动压缩），说不清楚也没关系。';

  return (
    <form className={styles.composer} onSubmit={(e) => { e.preventDefault(); void submit(); }} aria-label={receipt ? '上传购买凭证' : '发送消息'}>
      <div className={styles.heading}>
        <label htmlFor={inputId}>{receipt ? '凭证备注（选填）' : '描述你的问题'}</label>
        <span>{receipt ? '订单截图、发票或收据均可' : cardOnly ? '请先完成上方卡片' : '直接输入，不用先选产品'}</span>
      </div>
      <div className={styles.box}>
        <textarea id={inputId} ref={inputRef} className={styles.input} rows={3} maxLength={4000} value={value}
          disabled={cardOnly || runBusy || submitting} onChange={(e) => onChange(e.target.value)}
          placeholder={receipt ? '可补充购买平台、店铺或其他需要说明的信息…' : '点击这里输入，例如：我的耳机只有一边有声音，重置后还是不行…'}
          aria-describedby={`${inputId}-hint`} />
        {attachments.length > 0 && (
          <ul className={styles.attachments} aria-label="待发送图片">
            {attachments.map((item, i) => (
              <li key={item.id}>
                {item.previewUrl ? <img src={item.previewUrl} alt={`待发送图片 ${i + 1}`} /> : <span className={styles.thumbFallback}>图 {i + 1}</span>}
                <span className={styles.fileMeta}>{(item.file.size / 1024).toFixed(0)} KB</span>
                <button type="button" disabled={runBusy || busy} onClick={() => remove(item.id)} aria-label={`移除图片 ${i + 1}`}>×</button>
              </li>
            ))}
          </ul>
        )}
        <div className={styles.tools}>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden disabled={inputBlocked} data-testid="image-input"
            onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ''; }} />
          <button type="button" className={styles.tool} disabled={inputBlocked} title={receipt ? '选择购买凭证图片' : '上传故障照片'} onClick={() => fileRef.current?.click()}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 8" /></svg>
            <span>{processing ? '处理中…' : receipt ? '选择凭证图片' : '照片'}</span>
          </button>
          <button type="button" className={styles.human} disabled={offline || !onRequestHuman} onClick={onRequestHuman}>请求人工</button>
          {runBusy && onCancel && <button type="button" className={styles.human} onClick={onCancel}>取消</button>}
          <button type="submit" className={styles.send} disabled={!canSend}>{submitting ? '提交中…' : receipt ? '上传凭证' : '发送'}</button>
        </div>
      </div>
      {receipt && onSkipReceipt && (
        <div className={styles.skipOptions} aria-label="暂不上传凭证">
          <span>暂不上传：</span>
          <button type="button" disabled={inputBlocked} onClick={() => void skip('none')}>没有凭证，跳过</button>
          <button type="button" disabled={inputBlocked} onClick={() => void skip('unreadable')}>看不清，跳过</button>
          <button type="button" disabled={inputBlocked} onClick={() => void skip('later')}>稍后再提供</button>
        </div>
      )}
      {imageError && <p role="alert" className={styles.imageError}>{imageError}</p>}
      <p id={`${inputId}-hint`} className={styles.hintText}>{hint}</p>
    </form>
  );
}
