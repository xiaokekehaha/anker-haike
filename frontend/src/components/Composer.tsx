import { useEffect, useId, useRef, useState } from 'react';
import type { ClipboardEvent as ReactClipboardEvent, KeyboardEvent as ReactKeyboardEvent, Ref, RefObject } from 'react';
import { clipboardImages, isTouchPrimary, TOUCH_PRIMARY_QUERY } from '../lib/device';
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
  /** 外部预置的附件（「载入真实工单」带的原图）；引用变化时加入附件区，走与手动选择相同的处理。 */
  presetFiles?: File[] | null;
};

// 等待步骤时仍可正常对话，是否更新排障由本轮语义决定。
export const REDIAGNOSE_HINT = '可以追问原因、回顾记录、补充或纠正情况；完成操作后，也可以直接描述结果。';
let seq = 0;
function makePreview(file: File): string | null {
  try { return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null; }
  catch { return null; }
}
/** 触屏设备上回车换行；桌面端回车发送。设备可能中途变化（外接键盘、平板切换），所以跟随媒体查询。 */
function useTouchPrimary(): boolean {
  const [touch, setTouch] = useState(isTouchPrimary);
  useEffect(() => {
    const query = typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(TOUCH_PRIMARY_QUERY) : null;
    if (!query?.addEventListener) return;
    const onChange = (e: MediaQueryListEvent) => setTouch(e.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return touch;
}

function release(items: Attachment[]) {
  for (const item of items) if (item.previewUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(item.previewUrl);
}

/** 单行起步、随内容长高到约 6 行的输入框：卡片在场时它只是「补一句」的位置，不该是 100 px 的大文本域。 */
function autoGrow(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
}

export function Composer({ value, onChange, offline, inputRef, onSend, onRequestHuman, onSkipReceipt, pendingKind = null, purpose = 'fault', maxImages = 3, busy: runBusy = false, onCancel, presetFiles = null }: Props) {
  const inputId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const localRef = useRef<HTMLTextAreaElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const attachmentsRef = useRef<Attachment[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const processingRef = useRef(false);
  const composingRef = useRef(false);
  const submittingRef = useRef(false);
  const generation = useRef(0);
  const touchPrimary = useTouchPrimary();
  const receipt = pendingKind === 'upload_receipt';
  const rediagnose = pendingKind === 'step_feedback';
  const busy = processing || submitting;
  const inputBlocked = !!offline || runBusy || busy;
  const hasContent = value.trim().length > 0 || attachments.length > 0;
  const canSend = !inputBlocked && !!onSend && hasContent;

  useEffect(() => { autoGrow(localRef.current); }, [value]);

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

  useEffect(() => {
    if (presetFiles?.length) {
      release(attachmentsRef.current);
      updateAttachments([]);
      void addFiles(presetFiles.slice(0, maxImages));
    }
    // 只在载入新工单（新数组引用）时触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetFiles]);

  function setRefs(el: HTMLTextAreaElement | null) {
    localRef.current = el;
    if (typeof inputRef === 'function') inputRef(el);
    else if (inputRef) (inputRef as RefObject<HTMLTextAreaElement | null>).current = el;
  }

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

  /** 桌面端 Enter 发送、Shift+Enter 换行；Cmd/Ctrl+Enter 任何设备都发送。
   *  中文输入法选词时的回车属于候选确认（isComposing / keyCode 229），不能当作发送。 */
  function onKeyDown(e: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter' || e.shiftKey || e.altKey) return;
    if (composingRef.current || e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    const withModifier = e.metaKey || e.ctrlKey;
    if (!withModifier && touchPrimary) return;
    e.preventDefault();
    void submit();
  }

  /** 截图直接粘贴进输入框；纯文本粘贴保持浏览器默认行为。 */
  function onPaste(e: ReactClipboardEvent<HTMLTextAreaElement>) {
    const images = clipboardImages(e.clipboardData);
    if (!images.length) return;
    e.preventDefault();
    void addFiles(images);
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
    : rediagnose ? REDIAGNOSE_HINT
    : receipt ? '请上传订单截图、发票或收据，可附带备注；单张 5 MB 内。也可以跳过，由人工协助核实。'
    : '支持文字与图片（单张 5 MB 内，会自动压缩），说不清楚也没关系。';
  // 键盘用法只在能用上的设备提示；离线时发不出去，不提发送键。
  const keyHint = offline || touchPrimary ? null : 'Enter 发送，Shift+Enter 换行，截图可直接粘贴到输入框。';
  const label = receipt ? '凭证备注（选填）' : rediagnose ? '补充新情况或纠正' : '描述你的问题';
  const placeholder = receipt ? '可补充购买平台、店铺或其他需要说明的信息…'
    : rediagnose ? '也可以直接描述结果，例如：其实还有异响 / 说错了，我的是 Omni E28…'
    : '说说设备型号和问题，例如：Omni E25 报 3212 错误，滚刷拖布卡住了；也可以直接贴 App 报错或订单号…';

  return (
    <form className={styles.composer} onSubmit={(e) => { e.preventDefault(); void submit(); }} aria-label={receipt ? '上传购买凭证' : '发送消息'}>
      <label htmlFor={inputId} className={styles.label}>{label}</label>
      <div className={styles.box} data-receipt={receipt || undefined}>
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
        <div className={styles.row}>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden disabled={inputBlocked} data-testid="image-input"
            onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ''; }} />
          <button type="button" className={styles.tool} disabled={inputBlocked} aria-label={processing ? '图片处理中' : receipt ? '选择凭证图片' : '上传故障照片'} title={receipt ? '选择购买凭证图片' : '上传故障照片'} onClick={() => fileRef.current?.click()}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 8" /></svg>
          </button>
          <textarea id={inputId} ref={setRefs} className={styles.input} rows={1} maxLength={4000} value={value}
            disabled={runBusy || submitting} onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown} onPaste={onPaste}
            onCompositionStart={() => { composingRef.current = true; }} onCompositionEnd={() => { composingRef.current = false; }}
            placeholder={placeholder}
            aria-describedby={keyHint ? `${inputId}-hint ${inputId}-keys` : `${inputId}-hint`} />
          {runBusy && onCancel && <button type="button" className={styles.ghost} onClick={onCancel}>取消</button>}
          {onRequestHuman && <button type="button" className={styles.ghost} disabled={offline} onClick={onRequestHuman}>请求人工</button>}
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
      {keyHint && <p id={`${inputId}-keys`} className={styles.hintText}>{keyHint}</p>}
    </form>
  );
}
