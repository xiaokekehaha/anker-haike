import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { NodeDetail } from '../components/NodeDetail';
import { Journey } from '../pages/Journey';
import type { Journey as JourneyData } from '../types';

vi.mock('../api', () => ({ api: { journey: vi.fn(), topology: vi.fn().mockResolvedValue({ nodes: [], edges: [], stage_order: [] }) } }));
vi.mock('../components/GraphView', () => ({ GraphView: () => null }));

const data: JourneyData = {
  session: {
    session_id: 'session', created_at: '', last_run_at: '', runs: 7, first_question: '737 充电慢',
    sku: 'ANKER-A1289', category: 'power_bank', product_state: 'confirmed', emotion_level: null,
    steps_executed: 0, knowledge_status: 'ok', outcome: 'escalated', outcome_reason: 'R2',
    model_calls: 0, tokens: 0, total_latency_ms: 0, fault_plan_ids: [], raw_available: true,
    case_verdict: null, case_tags: null,
  },
  runs: [], case: null,
  snapshot: { session_id: 'session', version: 7, stage: 'escalate', substage: null, timeline: [
    { kind: 'escalation_summary', card_id: 'summary', summary: {
      product: '737', problem: '充电慢', reason: { rule_id: 'R2', text: '现有资料没有适用的排查路径' },
    } },
  ] },
};

describe('旅程结束原因', () => {
  it('展示摘要中的实际原因，零步骤不标为耗尽', async () => {
    vi.mocked(api.journey).mockResolvedValue(data);
    render(<MemoryRouter><Journey /></MemoryRouter>);
    expect(await screen.findByText('原因 现有资料没有适用的排查路径')).toBeInTheDocument();
    expect(screen.getByText('7 轮 · 0 个步骤')).toBeInTheDocument();
    expect(screen.queryByText(/适用步骤已耗尽/)).not.toBeInTheDocument();
  });

  it('没有快照时 R2 使用中性描述', async () => {
    vi.mocked(api.journey).mockResolvedValue({ ...data, snapshot: null });
    render(<MemoryRouter><Journey /></MemoryRouter>);
    expect(await screen.findByText('原因 当前排查未能继续')).toBeInTheDocument();
  });

  it('已继续排查时不沿用旧摘要原因', async () => {
    vi.mocked(api.journey).mockResolvedValue({ ...data, session: { ...data.session, outcome: 'awaiting_user', outcome_reason: 'step_feedback' } });
    render(<MemoryRouter><Journey /></MemoryRouter>);
    expect(await screen.findByText('原因 等步骤反馈')).toBeInTheDocument();
  });

  it('展示本轮实际候选来源', async () => {
    vi.mocked(api.journey).mockResolvedValue({ ...data, runs: [{
      run_id: 'r', session_id: 'session', seq_no: 1, started_at: '', ended_at: null,
      duration_ms: 10, entry: 'message', stage_from: 'diagnose', stage_to: 'guide',
      done_reason: 'awaiting_input', error_code: null, first_visible_ms: null,
      card_ready_ms: null, card_kind: 'step_card', model_calls: 0, tokens_in: 0, tokens_out: 0,
      node_count: 1, retrieval_calls: [], nodes: [{
        run_id: 'r', idx: 1, node: 'reassess', prev_node: null, started_at: '', duration_ms: 10,
        status: 'ok', summary: { relaxed_level: 'observation' },
      }],
    }] });
    render(<MemoryRouter><Journey /></MemoryRouter>);
    expect(await screen.findByText('本轮候选评估：依据观察重选')).toBeInTheDocument();
  });

  it('节点详情展示排除原因计数，隐藏非枚举内容', () => {
    render(<NodeDetail models={[]} retrievals={[]} node={{
      run_id: 'r', idx: 1, node: 'reassess', prev_node: null, started_at: '', duration_ms: 10,
      status: 'ok', summary: { relaxed_level: 'observation', candidate_rejection_counts: {
        diagnostic_plan_constraint: 1, resource_unavailable: 2, '用户原话': 1,
      } },
    }} />);
    expect(screen.getByText('依据观察重选')).toBeInTheDocument();
    expect(screen.getByText('旧问诊限制 1 次；操作资源缺失 2 次')).toBeInTheDocument();
    expect(screen.queryByText(/用户原话/)).not.toBeInTheDocument();
  });
});
