import { useEffect, useRef, useState } from 'react';
import { HeaderBar } from './components/HeaderBar';
import { ChatPane } from './components/ChatPane';
import { Composer } from './components/Composer';
import { PendingCard, Timeline } from './components/Timeline';
import { RecordPanel } from './components/RecordPanel';
import { Toast } from './components/Toast';
import { SessionSwitcher } from './components/SessionSwitcher';
import { useHealth } from './state/useHealth';
import { useSession } from './state/useSession';
import { deriveRecord } from './state/record';
import cardStyles from './components/Cards.module.css';
import styles from './App.module.css';

/** 方案 A「服务台」：左对话（流 + 停靠待办）、右服务记录；手机端记录折成一条可展开的记录条。 */
export function App() {
  const health = useHealth();
  const session = useSession();
  const { state } = session;
  const [draft, setDraft] = useState('');
  const [hover, setHover] = useState<string[]>([]);
  const [recordOpen, setRecordOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const busy = state.ui === 'streaming' || state.ui === 'tool_running' || state.ui === 'recovering';
  const hasHistory = state.timeline.length > 0;
  const pendingKind = state.pendingInput?.kind ?? null;
  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const receiptUpload = pendingKind === 'upload_receipt';
  const composerContext = state.pendingInput?.card_id ?? 'message';
  useEffect(() => { setDraft(''); }, [composerContext]);

  // 新内容在下方：时间线变化时把流滚到底，待办卡本身在 dock 里不需要滚动去找
  const lastKey = state.timeline.length ? `${state.timeline.length}:${state.timeline[state.timeline.length - 1]?.kind}` : '';
  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lastKey, state.ui]);

  function pickPrompt(text: string) {
    setDraft(text);
    composerRef.current?.focus();
    requestAnimationFrame(() => {
      const input = composerRef.current;
      if (!input) return;
      input.setSelectionRange(input.value.length, input.value.length);
    });
  }

  const onAction = (kind: Parameters<typeof session.act>[0]['kind'], payload: Record<string, unknown>) => void session.act({ kind, payload });
  const onIssueAction = (kind: 'new_issue' | 'resume_issue', target_issue_id?: string) => void session.act({ kind, target_issue_id });
  const record = deriveRecord(state);
  const tried = record.steps.filter((s) => s.feedback).length;
  const stripText = [record.product?.name ?? (record.problem ? record.problem.slice(0, 24) : '新会话'), record.route.active >= 0 ? record.route.steps[record.route.active]?.label : null, record.steps.length ? `已试 ${tried} 步` : null].filter(Boolean).join(' · ');

  const panel = (
    <RecordPanel state={state} highlight={hover} busy={state.pendingActionId !== null}
      onRequestHuman={() => void session.requestHuman()}
      onNewIssue={state.id ? () => onIssueAction('new_issue') : undefined}
      onResumeIssue={(id) => onIssueAction('resume_issue', id)} />
  );

  return (
    <div className={styles.app} data-ui={state.ui}>
      <a href="#main" className={styles.skip}>跳到主要内容</a>
      <HeaderBar {...health}>
        <SessionSwitcher
          currentId={state.id}
          recent={session.recent}
          interruptible={busy || state.pendingInput !== null || state.activeRun !== null}
          busy={busy}
          onNew={() => void session.startNew()}
          onSwitch={(id) => void session.switchTo(id)}
        />
      </HeaderBar>
      {hasHistory && (
        <div className={styles.strip}>
          <span className={styles.stripText}>{stripText}</span>
          <button type="button" className={styles.stripButton} onClick={() => setRecordOpen(true)} aria-expanded={recordOpen}>查看记录</button>
        </div>
      )}
      <main id="main" className={styles.layout}>
        <section className={styles.conv} aria-label="智能售后对话">
          <div className={styles.stream} ref={streamRef}>
            {!hasHistory && <ChatPane onPick={pickPrompt} disabled={busy} />}
            <Timeline state={state} onAction={onAction} onHover={setHover} dockPending />
            {state.stalled && busy && <p className={cardStyles.stallNote} role="status">仍在处理，请稍候…</p>}
            {busy && !state.stalled && <p className={cardStyles.sysRow} role="status">{state.ui === 'tool_running' ? '正在检索知识库…' : state.ui === 'recovering' ? '正在恢复连接…' : '正在处理…'}</p>}
            {state.ui === 'failed' && (
              <p className={styles.failed} role="status">这一轮没有完成。{state.id && <button type="button" onClick={() => void session.recover()}>恢复连接</button>}</p>
            )}
          </div>
          <div className={styles.dock}>
            {pendingCard && <PendingCard state={state} onAction={onAction} onHover={setHover} />}
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
              onRequestHuman={hasHistory ? undefined : () => void session.requestHuman()}
              onCancel={state.activeRun ? () => void session.cancel() : undefined}
            />
          </div>
        </section>
        <aside className={styles.record} aria-label="服务记录">{panel}</aside>
      </main>
      {recordOpen && (
        <div className={styles.overlay} role="dialog" aria-label="服务记录">
          <div className={styles.overlayHead}><strong>服务记录</strong><button type="button" onClick={() => setRecordOpen(false)} aria-label="关闭服务记录">×</button></div>
          {panel}
        </div>
      )}
      {state.error && <Toast message={state.error.message || '出现了一个错误'} recoverable={state.error.recoverable} onClose={session.clearError} />}
    </div>
  );
}
