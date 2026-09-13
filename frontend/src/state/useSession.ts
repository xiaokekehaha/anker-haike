/** 会话生命周期：同一时刻只保留一个请求，恢复以快照为准，动作仅在服务端明确允许时重试。 */
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { ApiError, cancelRun, createSession, getSnapshot, newId, postAction, resumeEvents, sendMessage } from '../api/client';
import { readSSE } from '../api/sse';
import { makeTitle, removeRecent, touchRecent, useRecentSessions } from './recentSessions';
import type { ActionRequest } from '../types/actions';
import type { SessionSnapshot } from '../types/snapshot';
import { reducer } from './reducer';
import { initialState } from './types';
import type { SessionAction } from './types';

const STORAGE_KEY = 'haike.session_id';
const STALL_MS = 15_000;
const GRACE_MS = 5_000;
const MAX_RECONNECTS = 2;
export type SendOptions = { files?: File[]; purpose?: 'fault' | 'receipt' };

function noteSnapshot(id: string, snapshot: SessionSnapshot) {
  const first = snapshot.timeline?.find((item) => item.kind === 'user_message');
  touchRecent(id, { stage: snapshot.stage, title: first && 'text' in first ? makeTitle(first.text) : null });
}

export function useSession() {
  const [state, reactDispatch] = useReducer(reducer, initialState);
  const recent = useRecentSessions();
  // 同步投影保证同一批 SSE 的 done 在 React 下一次 render 前就可见。
  const stateRef = useRef(initialState);
  const operation = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const pendingSubmission = useRef<{ sessionId: string; inputId: string; text: string; purpose: string; files: File[] } | null>(null);
  const pendingAction = useRef<{ key: string; body: ActionRequest } | null>(null);
  const dispatch = useCallback((action: SessionAction) => {
    if (!mounted.current) return;
    stateRef.current = reducer(stateRef.current, action);
    reactDispatch(action);
  }, []);

  function begin() {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    return controller;
  }
  function current(controller: AbortController) {
    return mounted.current && operation.current === controller && !controller.signal.aborted;
  }
  function finish(controller: AbortController) {
    if (operation.current === controller) operation.current = null;
  }
  function fail(error: unknown, controller: AbortController) {
    if (current(controller)) dispatch({ type: 'stream_error', message: error instanceof Error ? error.message : '连接失败，请重试' });
  }

  async function consume(response: Response, controller: AbortController) {
    if (!response.body) throw new Error('服务未返回事件流');
    let terminal = false;
    let retryAllowed = false;
    let retry = false;
    await readSSE(response.body, (event) => {
      if (!current(controller)) return;
      if (event.type === 'error') retryAllowed = event.recoverable && event.retry_with_same_action === true;
      if (event.type === 'done') {
        terminal = true;
        retry = event.reason === 'error' && retryAllowed;
      }
      dispatch({ type: 'server_event', event });
      if (event.type === 'done') {
        // 本轮结束即把阶段写进最近列表，不用等下次恢复
        const s = stateRef.current;
        if (s.id) touchRecent(s.id, { stage: s.stage });
        return false;
      }
    }, controller.signal);
    return { terminal, retry };
  }

  async function restore(id: string, controller: AbortController, supplied?: SessionSnapshot) {
    // 快照固定事件水位，续接只追加水位之后的事件。
    for (let attempt = 0; attempt <= MAX_RECONNECTS && current(controller); attempt++) {
      dispatch({ type: 'recovering' });
      const snapshot = supplied ?? await getSnapshot(id, controller.signal);
      supplied = undefined;
      if (!current(controller)) return;
      dispatch({ type: 'restore', snapshot });
      noteSnapshot(id, snapshot);
      const active = snapshot.active_run;
      if (!active || new Date(active.deadline_at).getTime() + GRACE_MS <= Date.now()) return;
      try {
        const response = await resumeEvents(id, active.run_id, snapshot.last_event_seq ?? 0, controller.signal);
        if (!current(controller)) return;
        const result = await consume(response, controller);
        if (!current(controller)) return;
        if (result.terminal) {
          // 完成后重取权威卡片结果、用户消息 ID、pending 与取消状态。
          const finalSnapshot = await getSnapshot(id, controller.signal);
          if (current(controller)) { dispatch({ type: 'restore', snapshot: finalSnapshot }); noteSnapshot(id, finalSnapshot); }
          return;
        }
      } catch (error) {
        if (!current(controller)) return;
        if (attempt === MAX_RECONNECTS) throw error;
      }
    }
    if (current(controller)) throw new Error('连接多次中断，请点击恢复连接重试');
  }

  const recover = useCallback(async () => {
    const id = stateRef.current.id;
    if (!id) return;
    const controller = begin();
    try { await restore(id, controller); }
    catch (error) { fail(error, controller); }
    finally { finish(controller); }
    // 所有异步状态都从 ref 读取，回调不捕获 render 的旧值。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  /** 打开一个已存在的会话：写入本页引用并恢复；确定不存在（404）才移除本地引用与最近记录。 */
  function open(id: string) {
    const controller = begin();
    try { sessionStorage.setItem(STORAGE_KEY, id); } catch { /* storage unavailable */ }
    dispatch({ type: 'session_created', id, version: 0 });
    return restore(id, controller).catch((error: unknown) => {
      if (!current(controller)) return;
      // 网络错误保留会话，只有确定不存在才移除本地引用。
      if (error instanceof ApiError && error.status === 404) {
        try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* storage unavailable */ }
        removeRecent(id);
        dispatch({ type: 'reset' });
        dispatch({ type: 'notice', message: '该会话已过期或已删除，请开始新会话' });
      } else fail(error, controller);
    }).finally(() => finish(controller));
  }

  useEffect(() => {
    mounted.current = true;
    let saved: string | null = null;
    try { saved = sessionStorage.getItem(STORAGE_KEY); } catch { /* storage unavailable */ }
    if (saved) void open(saved);
    return () => { mounted.current = false; operation.current?.abort(); operation.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  useEffect(() => {
    const timer = setInterval(() => {
      const s = stateRef.current;
      if (s.ui !== 'streaming' && s.ui !== 'tool_running') return;
      if (s.lastEventAt !== null && Date.now() - s.lastEventAt > STALL_MS && !s.stalled) dispatch({ type: 'stall', stalled: true });
      if (s.activeRun && Date.now() > new Date(s.activeRun.deadline_at).getTime() + GRACE_MS) void recover();
    }, 1000);
    return () => clearInterval(timer);
  }, [dispatch, recover]);

  const send = useCallback(async (text: string, opts: SendOptions = {}): Promise<boolean> => {
    if (operation.current || stateRef.current.activeRun) return false;
    const files = opts.files ?? [];
    if (!text.trim() && files.length === 0) return false;
    text = text.trim();
    let accepted = false;
    const controller = begin();
    try {
      let id = stateRef.current.id;
      if (!id) {
        const created = await createSession(controller.signal);
        if (!current(controller)) return false;
        id = created.session_id;
        dispatch({ type: 'session_created', id, version: created.version });
        try { sessionStorage.setItem(STORAGE_KEY, id); } catch { /* storage unavailable */ }
      }
      const previous = pendingSubmission.current;
      const purpose = opts.purpose ?? 'fault';
      const same = previous?.sessionId === id && previous.text === text && previous.purpose === purpose && previous.files.length === files.length && previous.files.every((file, index) => file === files[index]);
      const inputId = same ? previous.inputId : newId();
      pendingSubmission.current = { sessionId: id, inputId, text, purpose, files: [...files] };
      dispatch({ type: 'user_send', id: inputId, text, at: new Date().toISOString() });
      touchRecent(id, { title: makeTitle(text) });
      let recovering = false;
      try {
        const response = await sendMessage(id, text, opts.files ?? [], opts.purpose ?? 'fault', inputId, stateRef.current.version, controller.signal);
        if (!current(controller)) return false;
        accepted = true;
        pendingSubmission.current = null;
        const result = await consume(response, controller);
        if (current(controller) && !result.terminal) { recovering = true; await restore(id, controller); }
        else if (current(controller) && files.length > 0) {
          const snapshot = await getSnapshot(id, controller.signal);
          if (current(controller)) dispatch({ type: 'restore', snapshot });
        }
      } catch (error) {
        if (!current(controller)) return false;
        if (recovering) throw error;
        if (error instanceof ApiError && error.status === 409 && error.snapshot) await restore(id, controller, error.snapshot);
        else if (!(error instanceof ApiError)) {
          const snapshot = await getSnapshot(id, controller.signal);
          accepted = (snapshot.timeline ?? []).some(item => item.kind === 'user_message' && item.id === inputId);
          if (accepted) pendingSubmission.current = null;
          await restore(id, controller, snapshot);
        }
        else throw error;
      }
    } catch (error) { fail(error, controller); }
    finally { finish(controller); }
    return accepted;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  const act = useCallback(async (partial: { kind: ActionRequest['kind']; payload?: Record<string, unknown>; target_issue_id?: string }) => {
    const s = stateRef.current;
    if (!s.id || (partial.kind !== 'request_human' && (operation.current || s.activeRun))) return;
    const controller = begin();
    let body = {
      action_id: newId(), expected_version: s.version, kind: partial.kind,
      ...(partial.kind === 'new_issue' || partial.kind === 'resume_issue' ? {} : { input_token: s.pendingInput?.input_token ?? null, card_id: s.pendingInput?.card_id ?? null }),
      ...(partial.kind === 'new_issue' ? { target_issue_id: null } : { target_issue_id: partial.target_issue_id ?? s.activeIssueId }),
      payload: partial.payload ?? {},
    } as ActionRequest;
    const actionKey = JSON.stringify({ sessionId: s.id, ...body, action_id: undefined, expected_version: undefined });
    if (pendingAction.current?.key === actionKey) body = { ...pendingAction.current.body, expected_version: s.version };
    pendingAction.current = { key: actionKey, body };
    dispatch({ type: 'action_sent', action_id: body.action_id, card_id: ('card_id' in body ? body.card_id : null) ?? '' });
    let recovering = false;
    try {
      for (let attempt = 0; attempt < 2 && current(controller); attempt++) {
        const response = await postAction(s.id, body, controller.signal);
        pendingAction.current = null;
        if (!current(controller)) return;
        const result = await consume(response, controller);
        if (!current(controller)) return;
        if (result.retry && attempt === 0) {
          dispatch({ type: 'action_sent', action_id: body.action_id, card_id: ('card_id' in body ? body.card_id : null) ?? '' });
          continue;
        }
        if (!result.terminal) { recovering = true; await restore(s.id, controller); }
        else if (!result.retry && !stateRef.current.error) {
          const snapshot = await getSnapshot(s.id, controller.signal);
          if (current(controller)) dispatch({ type: 'restore', snapshot });
        }
        break;
      }
    } catch (error) {
      if (!current(controller)) return;
      try {
        if (recovering) fail(error, controller);
        else if (error instanceof ApiError && error.status === 409 && error.snapshot) await restore(s.id, controller, error.snapshot);
        else if (!(error instanceof ApiError)) await restore(s.id, controller);
        else fail(error, controller);
      } catch (recoveryError) { fail(recoveryError, controller); }
    } finally {
      if (current(controller)) dispatch({ type: 'action_settled' });
      finish(controller);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  const cancel = useCallback(async () => {
    const s = stateRef.current;
    if (!s.id || !s.activeRun) return;
    const controller = begin();
    dispatch({ type: 'recovering' });
    try {
      await cancelRun(s.id, s.activeRun.run_id, controller.signal);
      if (current(controller)) await restore(s.id, controller);
    } catch (error) { fail(error, controller); }
    finally { finish(controller); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  const requestHuman = useCallback(() => act({ kind: 'request_human', payload: {} }), [act]);
  const reset = useCallback(() => {
    operation.current?.abort();
    operation.current = null;
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* storage unavailable */ }
    dispatch({ type: 'reset' });
  }, [dispatch]);

  /** 新建会话：有 active run 先取消（尽力而为），再清空本页引用；旧会话留在最近列表里可切回。 */
  const startNew = useCallback(async () => {
    const s = stateRef.current;
    if (s.id && s.activeRun) {
      const controller = begin();
      try { await cancelRun(s.id, s.activeRun.run_id, controller.signal); } catch { /* 服务端会按 deadline 自行结束 */ }
    }
    reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reset]);

  /** 切换到最近列表里的会话：不取消服务端 run，仅中止本页请求后按快照恢复。 */
  const switchTo = useCallback(async (id: string) => {
    if (!id || id === stateRef.current.id) return;
    await open(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  return { state, recent, send, act, cancel, requestHuman, recover, reset, startNew, switchTo, clearError: () => dispatch({ type: 'clear_error' }) };
}
