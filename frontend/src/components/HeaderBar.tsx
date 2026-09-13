import type { ComponentStatus, HealthState } from '../types/health';
import { useRef, useState } from 'react';
import { ModelDialog } from './ModelDialog';
import styles from './HeaderBar.module.css';

type Props = HealthState & { refresh: () => void };

function statusLabel(status: ComponentStatus | undefined, failed: boolean) {
  if (failed) return '连接异常';
  if (!status) return '检查中';
  if (status === 'ok') return '可用';
  if (status === 'unconfigured') return '未配置';
  return '不可用';
}

export function HeaderBar({ snapshot, error, refreshing, checkedAt, refresh }: Props) {
  const [modelsOpen, setModelsOpen] = useState(false);
  const modelsButton = useRef<HTMLButtonElement>(null);
  const services = [
    { key: 'weknora', label: '知识库', status: snapshot?.components.weknora.status },
    { key: 'db', label: '数据库', status: snapshot?.components.db.status },
  ];

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <a className={styles.brand} href="/" aria-label="Anker 智能服务首页">
          <span className={styles.mark} aria-hidden="true">✦</span>
          <span><strong>智能服务</strong><span className={styles.brandCaption}>ANKER · SMART CARE</span></span>
        </a>
        <div className={styles.health}>
          <button ref={modelsButton} className={styles.modelsButton} onClick={() => setModelsOpen(true)} aria-haspopup="dialog">
            <span>模型</span><span className={styles.serviceStatus}>查看连接状态 <span aria-hidden="true">↗</span></span>
          </button>
          {snapshot?.replay && (
            <span className={styles.replay} data-status={snapshot.replay.status} role="status"
              title={snapshot.replay.status === 'ok'
                ? `回放录制包 ${snapshot.replay.caseId}${snapshot.replay.title ? `：${snapshot.replay.title}` : ''}；模型与知识库均为录制结果`
                : `回放录制包 ${snapshot.replay.caseId} 与当前版本不符（replay_incompatible）`}>
              {snapshot.replay.status === 'ok' ? '演示回放' : '回放不可用'}
            </span>
          )}
          <ul className={styles.services} aria-label="组件健康状态" aria-live="polite" aria-atomic="true">
            {services.map(({ key, label, status }) => (
              <li key={key} className={styles.service}>
                <span className={styles.dot} data-status={error ? 'down' : status ?? 'checking'} aria-hidden="true" />
                <span>{label}<span className={styles.serviceStatus}>{statusLabel(status, !!error)}</span></span>
              </li>
            ))}
          </ul>
          <button className={styles.refresh} onClick={refresh} disabled={refreshing} aria-label="刷新服务状态"
            title={checkedAt ? `最近检查 ${checkedAt.toLocaleTimeString('zh-CN')}，每 10 秒自动刷新` : '每 10 秒自动刷新'}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.5-1L20 9M4 15l2.4 3A7 7 0 0 0 18 17" />
            </svg>
          </button>
        </div>
      </div>
      {modelsOpen && <ModelDialog onClose={() => { setModelsOpen(false); modelsButton.current?.focus(); }} />}
    </header>
  );
}
