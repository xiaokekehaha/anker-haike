import styles from './Cards.module.css';

export function Toast({ message, recoverable, onClose }: { message: string; recoverable: boolean; onClose: () => void }) {
  return (
    <div className={styles.toast} role="alert" data-recoverable={recoverable}>
      <span>{message}{recoverable ? '，可以稍后重试。' : ''}</span>
      <button type="button" onClick={onClose} aria-label="关闭提示">×</button>
    </div>
  );
}
