/** 只读时间线：直接消费快照，不复用聊天端组件（那些组件绑定会话状态与交互，
 *  管理端只要看，且要与聊天端解耦，互不影响改动）。 */
import { reasonText } from '../format';
import type { Snapshot, TimelineItem } from '../types';

export function ReadonlyTimeline({ snapshot }: { snapshot: Snapshot | null }) {
  if (!snapshot) {
    return (
      <p className="empty">
        原始会话已过保留期，只能看事实与节点轨迹。<br />
        演示期把 RETENTION_SESSION_HOURS 调大即可保留更久。
      </p>
    );
  }
  if (!snapshot.timeline.length) return <p className="empty">这次会话还没有内容。</p>;
  return (
    <div className="tl">
      {snapshot.timeline.map((item, i) => <Row key={key(item, i)} item={item} />)}
    </div>
  );
}

function key(item: TimelineItem, i: number): string {
  if ('card_id' in item) return item.card_id;
  if ('message_id' in item) return item.message_id;
  if ('id' in item) return item.id;
  if ('tool_id' in item) return item.tool_id;
  return `row-${i}`;
}

function Row({ item }: { item: TimelineItem }) {
  switch (item.kind) {
    case 'user_message':
      return (
        <div className="row user">
          {item.text}
          {item.image_ids?.length > 0 && <div className="meta">附 {item.image_ids.length} 张图片</div>}
        </div>
      );
    case 'assistant_message':
      return (
        <div className="row assistant">
          {item.text}
          {item.status !== 'completed' && <div className="meta">（{item.status === 'aborted' ? '已中断' : item.status}）</div>}
        </div>
      );
    case 'tool':
      return <div className="meta">工具 {item.name} · {item.status}{item.summary ? ` · ${item.summary}` : ''}</div>;
    case 'product_card':
      return (
        <div className="row card-item">
          <h4>产品确认</h4>
          <div className="meta">
            候选 {item.candidates.map((c) => c.name).join('、')}
            {item.selected_sku && ` · 用户选了 ${item.selected_sku}`}
          </div>
        </div>
      );
    case 'step_card':
      return (
        <div className="row card-item">
          <h4>步骤 · {item.step.title}</h4>
          <div>{item.step.instruction}</div>
          <div className="meta">
            预期：{item.step.expected_result}
            {item.feedback && ` · 用户反馈：${FEEDBACK[item.feedback] ?? item.feedback}`}
            {item.note && ` · 补充：${item.note}`}
          </div>
        </div>
      );
    case 'receipt_card':
      return (
        <div className="row card-item">
          <h4>购买凭证</h4>
          <div className="meta">{Object.entries(item.fields).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(' · ') || '未识别出字段'}</div>
        </div>
      );
    case 'evidence':
      return (
        <details className="row card-item">
          <summary className="meta">检索依据 {item.items.length} 条</summary>
          {item.items.map((e) => (
            <div key={e.evidence_id} className="meta" style={{ marginTop: 6 }}>
              {e.source} · {e.score.toFixed(4)}<br />{e.snippet}
            </div>
          ))}
        </details>
      );
    case 'escalation_summary':
      return (
        <div className="row card-item">
          <h4>升级摘要</h4>
          <div className="meta">
            {item.summary.product} · {item.summary.problem}<br />
            原因：{item.summary.reason.rule_id} {reasonText(item.summary.reason.rule_id)} · {item.summary.reason.text}
          </div>
        </div>
      );
    default:
      return null;
  }
}

const FEEDBACK: Record<string, string> = { solved: '已解决', not_solved: '没解决', cannot_do: '做不到' };
