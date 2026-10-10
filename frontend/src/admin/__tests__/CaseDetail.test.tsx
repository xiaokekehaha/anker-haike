/** 案件页：坐席打开待处理案件时，交接摘要、核对字段、质保判断、执行与承诺记录都在页面上，不用翻聊天记录。 */
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import type { ServiceCase } from '../l3';

const detail = vi.fn();
vi.mock('../l3', () => ({ l3Api: { detail: (...args: unknown[]) => detail(...args) } }));

const { CaseDetail } = await import('../pages/CaseDetail');

const CASE: ServiceCase = {
  case_id: 'c0ffee00-0000-4000-8000-000000000001', session_id: 's1', issue_id: 'i1', status: 'awaiting_approval',
  priority: 'normal', complaint_risk: false, revision: 7, opened_at: '2026-09-25T06:00:00Z', updated_at: '2026-09-25T06:05:00Z',
  owner: null, gate_result: null, snapshot: null,
  warranty: { status: 'in_warranty', basis: 'order', warranty_end: '2027-04-01', as_of: '2026-10-08', order_no: 'Anker016', reason: '订单 Anker016 质保至 2027-04-01' },
  external_refs: { order_no: 'Anker016' },
  proposal: { options: [{ option_id: 'replace', type: 'replace', title: '提交换货单', detail: '保内故障经排查仍未解决', source: 'sop' }], chosen_option_id: 'replace' },
  handoff_summary: {
    product: 'eufy Wearable Breast Pump S1 Pro', problem: '左侧无吸力', observations: ['图片：吸奶器机身'],
    steps: [{ step_id: 's1', title: '检查隔膜', feedback: 'not_solved' }, { step_id: 's2', title: '收到时按钮就坏了吗', answer: 'No' }],
    reason: { rule_id: 'R6', text: '提交条件未满足：缺少：产品 SN' },
    emotion: { level: 'calm', strategy: 'normal' },
    receipt: { status: 'order_verified', verified_facts: { order_no: 'Anker016', sku: 'T8D04121', amount: '349.99' } },
    draft_reply: '已整理订单、质保判断与证据，请核实后继续处理。',
  },
  executions: [{
    execution_id: 'e1', action_kind: 'service_order.create', status: 'failed', receipt: { status: 'failed' },
    error: { code: 'OutcomeUnverified', message: '办理结果暂时无法确认，为避免重复办理，已转人工核实。', recoverable: false, needs_review: true },
    gate_result: null, actions_version: 'a1', started_at: '2026-09-25T06:04:00Z',
  }],
  commitments: [{ text: '服务单已提交，人工处理中', source: 'receipt' }],
  events: [
    { seq: 1, type: 'status_changed', at: '2026-09-25T06:01:00Z', actor: 'system', payload: { from: 'proposing', to: 'awaiting_approval', reason: '需要人工审核' } },
    { seq: 2, type: 'request_changed', at: '2026-09-25T06:02:00Z', actor: 'user', payload: { input_id: 'x', quote: '还是改成退款吧', requested: 'refund' } },
  ],
};

function open(row: ServiceCase) {
  detail.mockResolvedValue(row);
  render(
    <MemoryRouter initialEntries={[`/desk/${row.case_id}`]}>
      <Routes><Route path="/desk/:id" element={<CaseDetail />} /></Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => detail.mockReset());

describe('CaseDetail', () => {
  test('交接摘要给出转人工原因、客户诉求、已做排查与核对字段', async () => {
    open(CASE);
    await waitFor(() => expect(screen.getByText('转人工原因：提交条件未满足：缺少：产品 SN')).toBeInTheDocument());
    expect(screen.getByText('左侧无吸力')).toBeInTheDocument();
    // 与对话侧摘要卡同款：操作卡记反馈，问句卡记回答
    expect(screen.getByText('检查隔膜（已操作，仍有问题）；收到时按钮就坏了吗（回答：No）')).toBeInTheDocument();
    expect(screen.getByText('订单金额')).toBeInTheDocument();
    expect(screen.getByText('349.99')).toBeInTheDocument();
    expect(screen.getByText('已整理订单、质保判断与证据，请核实后继续处理。')).toBeInTheDocument();
  });

  test('执行记录标出待人工核实，承诺带依据，事件时间线含客户变更原话', async () => {
    open(CASE);
    await waitFor(() => expect(screen.getByText('失败 · 待人工核实')).toBeInTheDocument());
    expect(screen.getByText('办理结果暂时无法确认，为避免重复办理，已转人工核实。')).toBeInTheDocument();
    expect(screen.getByText('服务单已提交，人工处理中')).toBeInTheDocument();
    expect(screen.getByText(/客户变更诉求：退款「还是改成退款吧」/)).toBeInTheDocument();
    expect(screen.getByText(/等待人工审核：需要人工审核/)).toBeInTheDocument();
  });

  test('质保判断写明依据与判断日期', async () => {
    open(CASE);
    expect((await screen.findAllByText(/订单 Anker016 质保至 2027-04-01/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/依据：订单质保结束日期 · 按 2026-10-08 计/)).toBeInTheDocument();
  });

  test('尚未交接的案件说明没有摘要', async () => {
    open({ ...CASE, handoff_summary: null, executions: [], commitments: [], events: [] });
    await waitFor(() => expect(screen.getByText('案件尚未交接人工，没有交接摘要。')).toBeInTheDocument());
    expect(screen.getByText('尚未执行办理动作。')).toBeInTheDocument();
  });
});
