import type { ServerEvent, Stage } from '../types/events';
import type { PendingInput, SessionSnapshot, TimelineItem } from '../types/snapshot';

export type UiState = 'idle' | 'streaming' | 'tool_running' | 'awaiting_input' | 'failed' | 'recovering';

export type ActiveRun = { run_id: string; deadline_at: string; deadline_ms: number };

export type SessionState = {
  id: string | null;
  stage: Stage | null;
  substage: string | null;
  ui: UiState;
  version: number;
  activeRun: ActiveRun | null;
  pendingInput: PendingInput | null;
  timeline: TimelineItem[];
  /** 最近一条已处理事件的 seq（续接用） */
  lastSeq: number;
  /** 最近一条事件到达的时间戳（毫秒）；15 s 无事件提示「仍在处理」 */
  lastEventAt: number | null;
  stalled: boolean;
  error: { code: string; message: string; recoverable: boolean } | null;
  /** 已发出、等待服务端结果的 action_id（卡片置为 disabled） */
  pendingActionId: string | null;
};

export type SessionAction =
  | { type: 'server_event'; event: ServerEvent; at?: number }
  | { type: 'user_send'; id: string; text: string; imageIds?: string[]; at: string }
  | { type: 'action_sent'; action_id: string; card_id: string }
  | { type: 'action_settled' }
  | { type: 'restore'; snapshot: SessionSnapshot; now?: number }
  | { type: 'session_created'; id: string; version: number }
  | { type: 'stream_error'; message: string }
  | { type: 'stall'; stalled: boolean }
  | { type: 'recovering' }
  | { type: 'clear_error' }
  /** 不改变 ui 的提示（Toast），如切换到已过期会话 */
  | { type: 'notice'; message: string }
  | { type: 'reset' };

export const initialState: SessionState = {
  id: null,
  stage: null,
  substage: null,
  ui: 'idle',
  version: 0,
  activeRun: null,
  pendingInput: null,
  timeline: [],
  lastSeq: 0,
  lastEventAt: null,
  stalled: false,
  error: null,
  pendingActionId: null,
};
