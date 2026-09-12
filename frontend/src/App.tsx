import { HeaderBar } from './components/HeaderBar';
import { useHealth } from './state/useHealth';
import styles from './App.module.css';

export function App() {
  const health = useHealth();
  const status = health.error ? 'error' : health.snapshot?.status ?? 'checking';
  const statusText = {
    checking: '正在检查服务状态',
    ok: '基础服务已就绪',
    degraded: '部分服务暂不可用',
    error: '暂时无法连接服务',
  }[status];

  return (
    <div className={styles.app}>
      <a href="#main" className={styles.skip}>跳到主要内容</a>
      <HeaderBar {...health} />
      <main id="main" className={styles.main}>
        <div className={styles.sectionLabel}><span /> 扫地机器人 · 售后支持</div>
        <section className={styles.welcome} aria-labelledby="welcome-title">
          <div className={styles.intro}>
            <p className={styles.eyebrow}>每一个小问题，都值得被认真对待</p>
            <h1 id="welcome-title">一起，让清洁<br />回到<span>好状态。</span></h1>
            <p className={styles.description}>从了解你的设备开始，陪你一步步找到问题，<br className={styles.desktopBreak} />让日常清洁重新变得轻松。</p>
            <div className={styles.serviceTag}><span aria-hidden="true">✓</span> 有依据的排查，清楚易懂的指引</div>
          </div>
          <div className={styles.illustration} aria-hidden="true">
            <svg viewBox="0 0 380 320" className={styles.robot}>
              <ellipse cx="198" cy="267" rx="115" ry="18" fill="var(--art-shadow)" />
              <circle cx="191" cy="154" r="125" fill="none" stroke="var(--art-line)" strokeDasharray="3 8" />
              <circle cx="191" cy="154" r="103" fill="var(--art-bg)" />
              <path d="m87 215-26 13m40 3-9 27m194-40 23 15m-39-2 10 24" stroke="var(--art-stroke)" strokeWidth="6" strokeLinecap="round" />
              <ellipse cx="190" cy="179" rx="108" ry="85" fill="var(--art-body-side)" stroke="var(--art-stroke)" strokeWidth="2" />
              <ellipse cx="190" cy="162" rx="108" ry="85" fill="var(--art-body)" stroke="var(--art-stroke)" strokeWidth="2" />
              <ellipse cx="190" cy="159" rx="94" ry="72" fill="none" stroke="var(--art-line)" />
              <ellipse cx="190" cy="127" rx="30" ry="22" fill="var(--art-body-side)" stroke="var(--art-stroke)" strokeWidth="2" />
              <ellipse cx="190" cy="119" rx="30" ry="22" fill="var(--art-body)" stroke="var(--art-stroke)" strokeWidth="2" />
              <ellipse cx="190" cy="119" rx="18" ry="12" fill="var(--art-bg)" />
              <rect x="181" y="176" width="18" height="27" rx="9" fill="var(--art-bg)" stroke="var(--art-stroke)" />
              <circle cx="190" cy="184" r="3" fill="var(--accent)" />
              <path d="M140 227q50 20 100 0" fill="none" stroke="var(--art-stroke)" strokeWidth="3" strokeLinecap="round" />
              <path d="m308 74 4 12 12 4-12 4-4 12-4-12-12-4 12-4zM66 119l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill="var(--accent)" />
              <circle cx="288" cy="238" r="22" fill="var(--accent)" /><path d="m278 238 7 7 13-14" fill="none" stroke="var(--on-accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </section>

        <section className={styles.workspace} aria-labelledby="workspace-title">
          <div className={styles.workspaceHeading}><h2 id="workspace-title">你的专属服务空间</h2><span>设备支持</span></div>
          <div className={styles.empty}>
            <span className={styles.chatIcon} aria-hidden="true">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M20 11a8 8 0 0 1-8 8H4v-8a8 8 0 1 1 16 0Z" /><path d="M8 10h8M8 14h5" /></svg>
            </span>
            <h3>对话服务准备中</h3>
            <p>当前可查看服务连接状态，对话功能将在后续开放。</p>
          </div>
          <div className={styles.statusPanel} data-status={status} role="status">
            <span className={styles.statusDot} aria-hidden="true" />
            <div><strong>{statusText}</strong><p>{health.error ?? (status === 'degraded' ? '请查看顶部状态灯，服务恢复后会自动更新。' : '每 10 秒自动检查；模型状态仅表示当前配置。')}</p></div>
            <button onClick={health.refresh} disabled={health.refreshing}>{health.refreshing ? '检查中…' : '重新检查'}<span aria-hidden="true"> ↗</span></button>
          </div>
        </section>
        <footer className={styles.footer}><span>耐心倾听 · 清晰指引 · 一步一步</span><span>ANKER SMART CARE</span></footer>
      </main>
    </div>
  );
}
