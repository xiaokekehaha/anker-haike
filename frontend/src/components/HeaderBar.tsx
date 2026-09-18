import type { ComponentStatus, HealthState } from '../types/health';
import type { ReactNode } from 'react';
import { useRef, useState } from 'react';
import { ModelDialog } from './ModelDialog';
import styles from './HeaderBar.module.css';

type Props = HealthState & { refresh: () => void; children?: ReactNode };

function statusLabel(status: ComponentStatus | undefined, failed: boolean) {
  if (failed) return '连接异常';
  if (!status) return '检查中';
  if (status === 'ok') return '可用';
  if (status === 'unconfigured') return '未配置';
  return '不可用';
}

/** 48 px 头部：品牌 + 会话切换 + 一个服务状态点。组件明细（模型 / 知识库 / 数据库）是运维信息，收进点开的弹层。 */
export function HeaderBar({ snapshot, error, refreshing, checkedAt, refresh, children }: Props) {
  const [modelsOpen, setModelsOpen] = useState(false);
  const modelsButton = useRef<HTMLButtonElement>(null);
  const services = [
    { key: 'weknora', label: '知识库', status: snapshot?.components.weknora.status },
    { key: 'db', label: '数据库', status: snapshot?.components.db.status },
  ];
  const overall: ComponentStatus | 'checking' | 'down' = error ? 'down' : !snapshot ? 'checking' : services.every((s) => s.status === 'ok') ? 'ok' : 'down';
  const overallLabel = error ? '服务连接异常' : !snapshot ? '检查中…' : overall === 'ok' ? '服务正常' : '服务部分不可用';

  return (
    <header className={styles.header}>
      <a className={styles.brand} href="/" aria-label="Anker 智能服务首页">
        <span className={styles.mark} aria-hidden="true">✦</span>
        <span className={styles.brandText}><strong>智能服务</strong><span className={styles.brandCaption}>ANKER · SMART CARE</span></span>
      </a>
      <div className={styles.center}>{children}</div>
      <div className={styles.health}>
        {snapshot?.replay && (
          <span className={styles.replay} data-status={snapshot.replay.status} role="status"
            title={snapshot.replay.status === 'ok'
              ? `回放录制包 ${snapshot.replay.caseId}${snapshot.replay.title ? `：${snapshot.replay.title}` : ''}；模型与知识库均为录制结果`
              : `回放录制包 ${snapshot.replay.caseId} 与当前版本不符（replay_incompatible）`}>
            {snapshot.replay.status === 'ok' ? '演示回放' : '回放不可用'}
          </span>
        )}
        <details className={styles.status}>
          <summary className={styles.statusSummary} aria-label="服务状态"><span className={styles.dot} data-status={overall} aria-hidden="true" /><span className={styles.statusText}>{overallLabel}</span></summary>
          <div className={styles.popover}>
            <ul className={styles.services} aria-label="组件健康状态" aria-live="polite" aria-atomic="true">
              {services.map(({ key, label, status }) => (
                <li key={key} className={styles.service}>
                  <span className={styles.dot} data-status={error ? 'down' : status ?? 'checking'} aria-hidden="true" />
                  <span>{label}</span><span className={styles.serviceStatus}>{statusLabel(status, !!error)}</span>
                </li>
              ))}
            </ul>
            <div className={styles.popoverActions}>
              <button ref={modelsButton} type="button" className={styles.modelsButton} onClick={() => setModelsOpen(true)} aria-haspopup="dialog">模型连接状态</button>
              <button type="button" className={styles.refresh} onClick={refresh} disabled={refreshing} aria-label="刷新服务状态"
                title={checkedAt ? `最近检查 ${checkedAt.toLocaleTimeString('zh-CN')}，每 10 秒自动刷新` : '每 10 秒自动刷新'}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                  <path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.5-1L20 9M4 15l2.4 3A7 7 0 0 0 18 17" />
                </svg>
              </button>
            </div>
          </div>
        </details>
      </div>
      {modelsOpen && <ModelDialog onClose={() => { setModelsOpen(false); modelsButton.current?.focus(); }} />}
    </header>
  );
}
