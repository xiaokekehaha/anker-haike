/** 只读会话视图：把权威快照喂给聊天端 reducer 的 restore，再用聊天端的 Timeline / RecordPanel 渲染。
 *  坐席看到的就是客户看到的，不再维护第二套只读渲染器。 */
import { useMemo } from 'react';
import { RecordPanel } from '../../components/RecordPanel';
import { Timeline } from '../../components/Timeline';
import { reducer } from '../../state/reducer';
import { initialState, type SessionState } from '../../state/types';
import type { SessionSnapshot } from '../../types/snapshot';

const noop = () => {};

export function useSnapshotState(snapshot: SessionSnapshot | null | undefined): SessionState | null {
  return useMemo(() => (snapshot ? reducer(initialState, { type: 'restore', snapshot }) : null), [snapshot]);
}

export function SessionView({ snapshot, onHover }: { snapshot: SessionSnapshot | null | undefined; onHover?: (ids: string[]) => void }) {
  const state = useSnapshotState(snapshot);
  if (!state) {
    return (
      <p className="empty">
        原始会话已过保留期，只能看事实与节点轨迹。<br />
        演示期把 RETENTION_SESSION_HOURS 调大即可保留更久。
      </p>
    );
  }
  if (!state.timeline.length) return <p className="empty">这次会话还没有内容。</p>;
  return <div className="session-view"><Timeline state={state} onAction={noop} onHover={onHover} readOnly /></div>;
}

/** 服务记录（客户端右栏同款），只读。 */
export function SessionRecord({ snapshot, highlight }: { snapshot: SessionSnapshot | null | undefined; highlight?: string[] }) {
  const state = useSnapshotState(snapshot);
  if (!state) return <p className="empty">没有可用的会话快照。</p>;
  return <RecordPanel state={state} highlight={highlight} />;
}
