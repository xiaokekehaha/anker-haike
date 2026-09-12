import { useRef, useState } from 'react';
import { HeaderBar } from './components/HeaderBar';
import { ProgressBar } from './components/ProgressBar';
import { ChatPane } from './components/ChatPane';
import { Composer } from './components/Composer';
import { useHealth } from './state/useHealth';
import styles from './App.module.css';

/** 对话后端（票 05/06）接通前，前端为只读壳：可浏览、可填草稿，不可发送 */
const CHAT_OFFLINE = true;

export function App() {
  const health = useHealth();
  const [draft, setDraft] = useState('');
  const composerRef = useRef<HTMLTextAreaElement>(null);
  function pickPrompt(text: string) {
    setDraft(text);
    // 用户主动选择快捷项时，将注意力和输入焦点一起带回编辑区。
    composerRef.current?.focus();
    requestAnimationFrame(() => {
      const input = composerRef.current;
      if (!input) return;
      input.setSelectionRange(input.value.length, input.value.length);
      const bounds = input.getBoundingClientRect();
      if (bounds.top < 0 || bounds.bottom > window.innerHeight) {
        input.scrollIntoView({ block: 'center', behavior: 'auto' });
      }
    });
  }
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
        <section className={styles.welcome} aria-labelledby="welcome-title">
          <p className={styles.eyebrow}>ANKER 全线智能硬件 · 售后服务</p>
          <h1 id="welcome-title">真正听懂，真正<span>解决。</span></h1>
          <p className={styles.description}>
            说说你的设备遇到了什么问题，或需要哪方面的售后帮助。我们会陪你一步步解决。
          </p>
          <ul className={styles.promises} aria-label="服务承诺">
            <li><span aria-hidden="true">✓</span>先安抚，再排查</li>
            <li><span aria-hidden="true">✓</span>每一步都有依据</li>
            <li><span aria-hidden="true">✓</span>解决不了就转人工，不用重复描述</li>
          </ul>
        </section>

        <section className={styles.workspace} aria-labelledby="workspace-title">
          <div className={styles.workspaceHeading}>
            <h2 id="workspace-title">智能售后对话</h2>
            <span className={styles.statusChip} data-status={status} role="status">
              <span className={styles.statusDot} aria-hidden="true" />{statusText}
              <button onClick={health.refresh} disabled={health.refreshing} aria-label="重新检查服务状态">{health.refreshing ? '检查中…' : '重新检查'}</button>
            </span>
          </div>
          <ProgressBar stage={null} />
          <ChatPane onPick={pickPrompt}>
            <Composer inputRef={composerRef} value={draft} onChange={setDraft} offline={CHAT_OFFLINE} />
          </ChatPane>
          {(status === 'degraded' || status === 'error') && (
            <p className={styles.degradedNote}>{health.error ?? '部分组件暂不可用，请查看顶部状态灯，恢复后会自动更新。'}</p>
          )}
        </section>
        <footer className={styles.footer}><span>听懂需求 · 分清产品 · 一步一步解决</span><span>ANKER SMART CARE</span></footer>
      </main>
    </div>
  );
}
