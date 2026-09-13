/** 标注面板：好 / 坏 / 待复盘 + 固定原因标签 + 备注。标签集合由后端给（与服务端校验同一份）。 */
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { TAG_TEXT, VERDICT_TEXT } from '../format';
import { useAsync } from '../useAsync';
import type { CaseRow } from '../types';

export function LabelDialog({ sessionId, current, onClose, onSaved }: {
  sessionId: string;
  current: CaseRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cases = useAsync(() => api.cases({}), []);
  const [verdict, setVerdict] = useState(current?.verdict ?? 'review');
  const [tags, setTags] = useState<string[]>(current?.reason_tags ?? []);
  const [note, setNote] = useState(current?.note ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { ref.current?.showModal(); }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.labelCase({ session_id: sessionId, verdict, reason_tags: tags, note: note || undefined });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  const available = cases.data?.reason_tags ?? Object.keys(TAG_TEXT);

  return (
    <dialog className="sheet" ref={ref} onClose={onClose} aria-label="标注会话">
      <h3>标注这个会话</h3>
      <div className="filters">
        {(['good', 'bad', 'review'] as const).map((v) => (
          <button key={v} className="chip" aria-pressed={verdict === v} onClick={() => setVerdict(v)}>
            {VERDICT_TEXT[v]}
          </button>
        ))}
      </div>
      <p className="sub" style={{ marginTop: 10 }}>原因标签（可多选，用于复盘时按原因归类）</p>
      <div className="chips">
        {available.map((tag) => (
          <button key={tag} className="chip" aria-pressed={tags.includes(tag)}
            onClick={() => setTags((t) => (t.includes(tag) ? t.filter((x) => x !== tag) : [...t, tag]))}>
            {TAG_TEXT[tag] ?? tag}
          </button>
        ))}
      </div>
      <p className="sub" style={{ marginTop: 12 }}>备注</p>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="这次为什么好 / 为什么不好，后续怎么改" />
      {error && <p style={{ color: 'var(--danger)', fontSize: 12.5 }}>{error}</p>}
      <div className="sheet-actions">
        <button className="btn" onClick={() => ref.current?.close()}>取消</button>
        <button className="btn" data-variant="primary" disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </dialog>
  );
}
