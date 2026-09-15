/** 新建会话 + 本机最近会话切换（spec_session_switch）。列表只来自本浏览器，跨设备属第二阶段。 */
import type { RecentSession } from '../state/recentSessions';
import { progressFor } from '../state/progress';
import styles from './SessionSwitcher.module.css';

type Props = {
  currentId: string | null;
  recent: RecentSession[];
  /** 正在运行 / 恢复，或有待输入卡片：新建前要确认 */
  interruptible: boolean;
  busy: boolean;
  onNew: () => void;
  onSwitch: (id: string) => void;
};

export function optionLabel(s: RecentSession, isCurrent: boolean): string {
  const time = new Date(s.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  const title = s.title ?? `新会话 · ${time}`;
  const stage = progressFor(s.stage, s.case_status).label;
  return `${isCurrent ? '（当前）' : ''}${title}${stage ? ` · ${stage}` : ''}`;
}

export function SessionSwitcher({ currentId, recent, interruptible, busy, onNew, onSwitch }: Props) {
  // 当前会话尚未写入列表（刚创建）时也要能显示为选中项
  const options = currentId && !recent.some((s) => s.id === currentId)
    ? [{ id: currentId, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), title: null, stage: null }, ...recent]
    : recent;

  function handleNew() {
    if (interruptible && !window.confirm('当前排查会中断，确定开始新会话？旧会话仍可从列表切回。')) return;
    onNew();
  }

  return (
    <div className={styles.switcher}>
      {options.length > 0 && (
        <select
          className={styles.select}
          aria-label="切换会话"
          value={currentId ?? ''}
          disabled={busy}
          onChange={(e) => { if (e.target.value && e.target.value !== currentId) onSwitch(e.target.value); }}
        >
          {!currentId && <option value="">新会话（未开始）</option>}
          {options.map((s) => <option key={s.id} value={s.id}>{optionLabel(s, s.id === currentId)}</option>)}
        </select>
      )}
      <button type="button" className={styles.newButton} onClick={handleNew} disabled={busy || !currentId} title={currentId ? '开始一个新会话；当前会话可从列表切回' : '当前已是新会话'}>
        <span aria-hidden="true">＋</span> 新建会话
      </button>
    </div>
  );
}
