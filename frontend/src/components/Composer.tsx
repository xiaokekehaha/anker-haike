import { useId, useRef, useState } from 'react';
import type { Ref } from 'react';
import { prepareImage } from '../lib/image';
import type { ImagePurpose } from '../lib/image';
import styles from './Composer.module.css';

export type Attachment = { id: string; file: File; previewUrl: string | null };

type Props = {
  value: string;
  onChange: (v: string) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  /** 对话后端未接通时传 true：输入可编辑但不可发送，并给出说明 */
  offline?: boolean;
  /** 发送：文字 + 已通过校验的图片（票 29）。未传时按钮只做表单占位。 */
  onSend?: (text: string, files: File[], purpose: ImagePurpose) => void;
  onRequestHuman?: () => void;
  purpose?: ImagePurpose;
  maxImages?: number;
};

let seq = 0;
function makePreview(file: File): string | null {
  try {
    return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null;
  } catch {
    return null;
  }
}

export function Composer({ value, onChange, offline, inputRef, onSend, onRequestHuman, purpose = 'fault', maxImages = 3 }: Props) {
  const inputId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canSend = !offline && !busy && (value.trim().length > 0 || attachments.length > 0);

  async function addFiles(list: FileList | File[]) {
    setImageError(null);
    const files = Array.from(list);
    if (files.length === 0) return;
    if (attachments.length + files.length > maxImages) {
      setImageError(`一次最多附带 ${maxImages} 张图片。`);
      return;
    }
    setBusy(true);
    const accepted: Attachment[] = [];
    const errors: string[] = [];
    for (const f of files) {
      const r = await prepareImage(f);
      if ('error' in r) errors.push(`${f.name}：${r.error}`);
      else accepted.push({ id: `img-${++seq}`, file: r.file, previewUrl: makePreview(r.file) });
    }
    setBusy(false);
    if (accepted.length) setAttachments((prev) => [...prev, ...accepted]);
    if (errors.length) setImageError(errors.join('；'));
  }

  function remove(id: string) {
    setAttachments((prev) => {
      const gone = prev.find((a) => a.id === id);
      if (gone?.previewUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(gone.previewUrl);
      return prev.filter((a) => a.id !== id);
    });
  }

  function submit() {
    if (!canSend) return;
    onSend?.(value.trim(), attachments.map((a) => a.file), purpose);
    attachments.forEach((a) => a.previewUrl && typeof URL.revokeObjectURL === 'function' && URL.revokeObjectURL(a.previewUrl));
    setAttachments([]);
    setImageError(null);
    onChange('');
  }

  return (
    <form className={styles.composer} onSubmit={(e) => { e.preventDefault(); submit(); }} aria-label="发送消息">
      <div className={styles.heading}>
        <label htmlFor={inputId}>描述你的问题</label>
        <span>直接输入，不用先选产品</span>
      </div>
      <div className={styles.box}>
        <textarea
          id={inputId}
          ref={inputRef}
          className={styles.input}
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="点击这里输入，例如：我的耳机只有一边有声音，重置后还是不行…"
          aria-describedby={`${inputId}-hint`}
        />
        {attachments.length > 0 && (
          <ul className={styles.attachments} aria-label="待发送图片">
            {attachments.map((a, i) => (
              <li key={a.id}>
                {a.previewUrl ? <img src={a.previewUrl} alt={`待发送图片 ${i + 1}`} /> : <span className={styles.thumbFallback}>图 {i + 1}</span>}
                <span className={styles.fileMeta}>{(a.file.size / 1024).toFixed(0)} KB</span>
                <button type="button" onClick={() => remove(a.id)} aria-label={`移除图片 ${i + 1}`}>×</button>
              </li>
            ))}
          </ul>
        )}
        <div className={styles.tools}>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            data-testid="image-input"
            onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ''; }}
          />
          <button type="button" className={styles.tool} disabled={offline || busy} title="上传故障照片或购买凭证" onClick={() => fileRef.current?.click()}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 8" /></svg>
            <span>{busy ? '处理中…' : '照片'}</span>
          </button>
          <button type="button" className={styles.human} disabled={offline} onClick={onRequestHuman}>请求人工</button>
          <button type="submit" className={styles.send} disabled={!canSend}>发送</button>
        </div>
      </div>
      {imageError && <p role="alert" className={styles.imageError}>{imageError}</p>}
      <p id={`${inputId}-hint`} className={styles.hintText}>
        {offline ? '可以先填写问题；对话服务暂未接通，目前无法发送。' : '支持文字与图片（单张 5 MB 内，会自动压缩），说不清楚也没关系。'}
      </p>
    </form>
  );
}
