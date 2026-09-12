import { useId } from 'react';
import type { Ref } from 'react';
import styles from './Composer.module.css';

type Props = {
  value: string;
  onChange: (v: string) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  /** 对话后端未接通时传 true：输入可编辑但不可发送，并给出说明 */
  offline?: boolean;
};

export function Composer({ value, onChange, offline, inputRef }: Props) {
  const inputId = useId();
  const canSend = !offline && value.trim().length > 0;
  return (
    <form className={styles.composer} onSubmit={(e) => e.preventDefault()} aria-label="发送消息">
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
        <div className={styles.tools}>
          <button type="button" className={styles.tool} disabled={offline} title="上传故障照片或购买凭证">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 8" /></svg>
            <span>照片</span>
          </button>
          <button type="button" className={styles.human} disabled={offline}>请求人工</button>
          <button type="submit" className={styles.send} disabled={!canSend}>发送</button>
        </div>
      </div>
      <p id={`${inputId}-hint`} className={styles.hintText}>
        {offline ? '可以先填写问题；对话服务暂未接通，目前无法发送。' : '支持文字与图片，说不清楚也没关系。'}
      </p>
    </form>
  );
}
