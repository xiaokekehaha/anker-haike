/** 案件页：坐席打开等审批案件时，交接摘要、核对字段、执行与承诺记录、条款来源都在页面上，不用翻聊天记录。 */
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
  owner: null, policy_decision: null, gate_result: null, snapshot: null,
  external_refs: { order_no: 'DEMO-X10-001' },
  proposal: { options: [{
    option_id: 'replace', remedy: 'replace', title: '申请换货', cost_bearer: 'company', auto_allowed: false,
    clauses: [{ clause_id: 'US-EUFY-12M', text: '整机 12 个月有限保修', source_doc: 'eufy 保修政策', source_url: 'https://example.com/warranty', doc_version: 'v1', policy_version: 'p1' }],
  }], chosen_option_id: 'replace' },
  handoff_summary: {
    product: 'eufy X10 Pro Omni', problem: '吸力下降', observations: ['图片：滚刷缠绕'],
    steps: [{ step_id: 's1', title: '清理滚刷', feedback: 'not_solved' }],
    reason: { rule_id: 'R6', text: '政策要求人工审核：跨区域使用需人工核实' },
    emotion: { level: 'calm', strategy: 'normal' },
    receipt: { status: 'order_verified', verified_facts: { order_no: 'DEMO-X10-001', sku: 'EUFY-X10-PRO-OMNI', amount: '449.99' } },
    draft_reply: '已整理订单与政策依据，请核实后继续处理。',
  },
  executions: [{
    execution_id: 'e1', action_kind: 'replacement.create', status: 'failed', receipt: { status: 'failed' },
    error: { code: 'OutcomeUnverified', message: '办理结果暂时无法确认，为避免重复办理，已转人工核实。', recoverable: false, needs_review: true },
    gate_result: null, policy_version: 'p1', actions_version: 'a1', started_at: '2026-09-25T06:04:00Z',
  }],
  commitments: [{ text: '申请换货；费用承担：company', source: 'clause' }],
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
    await waitFor(() => expect(screen.getByText('转人工原因：政策要求人工审核：跨区域使用需人工核实')).toBeInTheDocument());
    expect(screen.getByText('吸力下降')).toBeInTheDocument();
    expect(screen.getByText('清理滚刷（仍有问题）')).toBeInTheDocument();
    expect(screen.getByText('订单金额')).toBeInTheDocument();
    expect(screen.getByText('449.99')).toBeInTheDocument();
    expect(screen.getByText('已整理订单与政策依据，请核实后继续处理。')).toBeInTheDocument();
  });

  test('执行记录标出待人工核实，承诺带依据，事件时间线含客户变更原话', async () => {
    open(CASE);
    await waitFor(() => expect(screen.getByText('失败 · 待人工核实')).toBeInTheDocument());
    expect(screen.getByText('办理结果暂时无法确认，为避免重复办理，已转人工核实。')).toBeInTheDocument();
    expect(screen.getByText('申请换货；费用承担：company')).toBeInTheDocument();
    expect(screen.getByText(/客户变更诉求：退款「还是改成退款吧」/)).toBeInTheDocument();
    expect(screen.getByText(/等待人工审核：需要人工审核/)).toBeInTheDocument();
  });

  test('条款来源可以点开原文', async () => {
    open(CASE);
    const link = await screen.findByRole('link', { name: 'eufy 保修政策' });
    expect(link).toHaveAttribute('href', 'https://example.com/warranty');
  });

  test('尚未交接的案件说明没有摘要', async () => {
    open({ ...CASE, handoff_summary: null, executions: [], commitments: [], events: [] });
    await waitFor(() => expect(screen.getByText('案件尚未交接人工，没有交接摘要。')).toBeInTheDocument());
    expect(screen.getByText('尚未执行办理动作。')).toBeInTheDocument();
  });
});
