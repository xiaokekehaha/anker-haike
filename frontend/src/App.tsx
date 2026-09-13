import { useEffect, useRef, useState } from 'react';
import { HeaderBar } from './components/HeaderBar';
import { ProgressBar } from './components/ProgressBar';
import { ChatPane } from './components/ChatPane';
import { Composer } from './components/Composer';
import { Timeline } from './components/Timeline';
import { Toast } from './components/Toast';
import { SessionSwitcher } from './components/SessionSwitcher';
import { useHealth } from './state/useHealth';
import { useSession } from './state/useSession';
import cardStyles from './components/Cards.module.css';
import styles from './App.module.css';

const UI_TEXT: Record<string, string> = {
  idle: '', streaming: '正在处理…', tool_running: '正在检索知识库…', awaiting_input: '请在上方卡片中选择', failed: '这一轮没有完成', recovering: '正在恢复连接…',
};
// awaiting_input 按 pending kind 细分提示（票 34：步骤卡等待反馈）
const AWAITING_TEXT: Record<string, string> = {
  step_feedback: '请按步骤操作后，在卡片上告诉我结果；有新情况也可以直接补充', upload_receipt: '请上传购买凭证，或选择跳过', confirm_receipt: '请核对凭证信息后确认',
};

export function App() {
  const health = useHealth();
  const session = useSession();
  const { state } = session;
  const [draft, setDraft] = useState('');
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const busy = state.ui === 'streaming' || state.ui === 'tool_running' || state.ui === 'recovering';
  const hasHistory = state.timeline.length > 0;
  const pendingKind = state.pendingInput?.kind ?? null;
  const receiptUpload = pendingKind === 'upload_receipt';
  const composerContext = state.pendingInput?.card_id ?? 'message';
  useEffect(() => { setDraft(''); }, [composerContext]);

  function pickPrompt(text: string) {
    setDraft(text);
    composerRef.current?.focus();
    requestAnimationFrame(() => {
      const input = composerRef.current;
      if (!input) return;
      input.setSelectionRange(input.value.length, input.value.length);
      const bounds = input.getBoundingClientRect();
      if (bounds.top < 0 || bounds.bottom > window.innerHeight) input.scrollIntoView({ block: 'center', behavior: 'auto' });
    });
  }

  return (
    <div className={styles.app}>
      <a href="#main" className={styles.skip}>跳到主要内容</a>
      <HeaderBar {...health} />
      <main id="main" className={styles.main}>
        {!hasHistory && (
          <section className={styles.welcome} aria-labelledby="welcome-title">
            <p className={styles.eyebrow}>ANKER 全线智能硬件 · 售后服务</p>
            <h1 id="welcome-title">真正听懂，真正<span>解决。</span></h1>
            <p className={styles.description}>说说你的设备遇到了什么问题，或需要哪方面的售后帮助。我们会陪你一步步解决。</p>
            <ul className={styles.promises} aria-label="服务承诺">
              <li><span aria-hidden="true">✓</span>先安抚，再排查</li>
              <li><span aria-hidden="true">✓</span>每一步都有依据</li>
              <li><span aria-hidden="true">✓</span>整理问题记录，方便人工客服接续</li>
            </ul>
          </section>
        )}

        <section className={styles.workspace} aria-labelledby="workspace-title">
          <div className={styles.workspaceHeading}>
            <h2 id="workspace-title">智能售后对话</h2>
            <SessionSwitcher
              currentId={state.id}
              recent={session.recent}
              interruptible={busy || state.pendingInput !== null || state.activeRun !== null}
              busy={busy}
              onNew={() => void session.startNew()}
              onSwitch={(id) => void session.switchTo(id)}
            />
          </div>
          <ProgressBar stage={state.stage} />
          <ChatPane onPick={pickPrompt} disabled={busy} showStarters={!hasHistory}>
            <Timeline state={state} onAction={(kind, payload) => void session.act({ kind, payload })}
              onIssueAction={(kind, target_issue_id) => void session.act({ kind, target_issue_id })} />
            {state.stalled && busy && <p className={cardStyles.stallNote} role="status">仍在处理，请稍候…</p>}
            <p className={styles.uiState} data-ui={state.ui} role="status">{state.ui === 'awaiting_input' ? (AWAITING_TEXT[pendingKind ?? ''] ?? UI_TEXT.awaiting_input) : UI_TEXT[state.ui]}</p>
            {state.ui === 'failed' && state.id && <button onClick={() => void session.recover()}>恢复连接</button>}
            <Composer
              key={composerContext}
              pendingKind={pendingKind}
              purpose={receiptUpload ? 'receipt' : 'fault'}
              onSkipReceipt={(reason) => session.act({ kind: 'skip_receipt', payload: { reason } })}
              inputRef={composerRef}
              value={draft}
              onChange={setDraft}
              offline={false}
              busy={busy || state.pendingActionId !== null}
              onSend={(text, files, purpose) => session.send(text, { files, purpose })}
              onRequestHuman={() => void session.requestHuman()}
              onCancel={state.activeRun ? () => void session.cancel() : undefined}
            />
          </ChatPane>
        </section>
        <footer className={styles.footer}><span>听懂需求 · 分清产品 · 一步一步解决</span><span>ANKER SMART CARE</span></footer>
      </main>
      {state.error && <Toast message={state.error.message || '出现了一个错误'} recoverable={state.error.recoverable} onClose={session.clearError} />}
    </div>
  );
}
