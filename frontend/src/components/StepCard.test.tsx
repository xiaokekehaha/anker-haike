import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { StepCardItem, EvidenceItem } from '../types/snapshot';
import { EvidenceDrawer } from './EvidenceDrawer';
import { StepCard } from './StepCard';

const step = (over: Partial<StepCardItem['step']> = {}): StepCardItem['step'] => ({
  step_id: 's1', plan_id: 'qa_rv_0272', plan_version: 1, step_no: 1, title: '检查并清理滚刷',
  instruction: '把主机翻过来，取出滚刷，割断毛发后装回。', expected_result: '滚刷无缠绕物，转动顺畅', caution: null, evidence_ids: ['c12'], ...over,
});
const item = (over: Partial<StepCardItem> = {}): StepCardItem => ({ kind: 'step_card', card_id: 'k1', version: 3, step: step(), feedback: null, note: null, ...over });
const EVIDENCE: EvidenceItem[] = [
  { evidence_id: 'c12', source: 'kb_qa', doc_id: 'rv-0272', doc_version: '1', chunk_id: 'c12', snippet: 'Turn the robot over and remove the roller brush', score: 0.4, status: 'ok' },
  { evidence_id: 'c15', source: 'qa_exact', doc_id: 'rv-0306', doc_version: '1', chunk_id: 'c15', snippet: 'Remove and clean the filter', score: 0.2, status: 'ok' },
];

describe('StepCard（票 34）', () => {
  it('shows title, instruction, expected result, caution and source badge; posts feedback with note', () => {
    const onFeedback = vi.fn();
    render(<StepCard item={item({ step: step({ caution: '拆装前请先关机', evidence_ids: ['c12', 'c15'] }) })} active onFeedback={onFeedback} />);
    expect(screen.getByText('步骤 1：检查并清理滚刷')).toBeVisible();
    expect(screen.getByText('把主机翻过来，取出滚刷，割断毛发后装回。')).toBeVisible();
    expect(screen.getByText('滚刷无缠绕物，转动顺畅')).toBeVisible();
    expect(screen.getByRole('note')).toHaveTextContent('拆装前请先关机');
    expect(screen.getByText('依据 2')).toBeVisible();
    fireEvent.change(screen.getByLabelText('补充说明'), { target: { value: ' 还是没吸力 ' } });
    fireEvent.click(screen.getByRole('button', { name: '还没解决' }));
    expect(onFeedback).toHaveBeenCalledWith('not_solved', '还是没吸力');
    fireEvent.click(screen.getByRole('button', { name: '解决了' }));
    expect(onFeedback).toHaveBeenLastCalledWith('solved', '还是没吸力');
  });

  it('only the active card is interactive; answered old cards collapse to one line', () => {
    const onFeedback = vi.fn();
    const { container } = render(
      <>
        <StepCard item={item({ card_id: 'old', feedback: 'not_solved', note: '仍有异响' })} active={false} onFeedback={onFeedback} />
        <StepCard item={item({ card_id: 'cur', step: step({ step_id: 's2', step_no: 2, title: '取出并清洁滤网' }) })} active onFeedback={onFeedback} />
      </>,
    );
    const collapsed = container.querySelectorAll('[data-kind="step_card"]');
    expect(collapsed).toHaveLength(2);
    const first = collapsed[0]!;
    expect(first).toHaveTextContent('步骤 1：检查并清理滚刷');
    expect(first).toHaveTextContent('还没解决');
    expect(first.querySelectorAll('button')).toHaveLength(0);
    expect(screen.getAllByRole('button', { name: '解决了' })).toHaveLength(1);
    // 待反馈卡 disabled（动作进行中）时按钮不可点
    render(<StepCard item={item({ card_id: 'busy' })} active disabled onFeedback={onFeedback} />);
    const buttons = screen.getAllByRole('button', { name: '解决了' });
    expect(buttons[buttons.length - 1]).toBeDisabled();
  });

  it('answered active card shows the recorded feedback instead of buttons', () => {
    render(<StepCard item={item({ feedback: 'cannot_do', note: '没有工具' })} active onFeedback={vi.fn()} />);
    expect(screen.getByText('您的反馈：做不到 / 跳过（没有工具）')).toBeVisible();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('主引用直接展开，同 doc 的其余命中折叠一层', () => {
    const { container } = render(<EvidenceDrawer items={EVIDENCE} primary={['c12']} />);
    container.querySelector('details[data-testid="evidence-drawer"]')!.setAttribute('open', '');
    const main = container.querySelector('[data-testid="evidence-primary"]')!;
    expect(main.querySelectorAll('li')).toHaveLength(1);
    expect(main).toHaveTextContent('Turn the robot over and remove the roller brush');
    expect(screen.getByText('其他相关来源 1 条')).toBeVisible();
    expect(container.querySelector('li[data-primary]')).toHaveTextContent('Turn the robot over and remove the roller brush');
  });

  it('没有主引用时退回单一列表，不显示空的折叠层', () => {
    const { container } = render(<EvidenceDrawer items={EVIDENCE} />);
    expect(container.querySelector('[data-testid="evidence-primary"]')).toBeNull();
    expect(container.querySelector('[data-testid="evidence-others"]')).toBeNull();
    expect(container.querySelectorAll('li')).toHaveLength(2);
  });

  it('hovering a step card highlights its evidence_ids in the drawer', () => {
    function Harness() {
      const [hover, setHover] = React.useState<string[]>([]);
      return (
        <>
          <EvidenceDrawer items={EVIDENCE} highlight={hover} />
          <StepCard item={item()} active onFeedback={vi.fn()} onHover={setHover} />
        </>
      );
    }
    const { container } = render(<Harness />);
    const card = container.querySelector('section[data-kind="step_card"]')!;
    expect(container.querySelectorAll('li[data-highlight]')).toHaveLength(0);
    fireEvent.mouseEnter(card);
    const lit = container.querySelectorAll('li[data-highlight]');
    expect(lit).toHaveLength(1);
    expect(lit[0]).toHaveTextContent('Turn the robot over and remove the roller brush');
    expect(screen.getByText('（当前步骤引用 1 条）')).toBeInTheDocument();
    fireEvent.mouseLeave(card);
    expect(container.querySelectorAll('li[data-highlight]')).toHaveLength(0);
  });
});

describe('StepCard 的读图回显', () => {
  const base = {
    kind: 'step_card', card_id: 'c1', version: 1, at: '2026-09-15T00:00:00Z', seq: 1,
    step: { step_id: 's1', plan_id: 'p1', plan_version: 1, step_no: 1, title: '清理滚刷', instruction: '取下滚刷并剪掉缠绕的毛发。', expected_result: '滚刷可自由转动', evidence_ids: [] },
  } as unknown as StepCardItem;

  it('有 seen 时单独成行显示，不混进操作正文', () => {
    render(<StepCard item={{ ...base, seen: '从照片里我看到：滚刷缠绕。如果不对，您可以直接告诉我。' } as StepCardItem} active onFeedback={vi.fn()} />);
    const echo = screen.getByText(/从照片里我看到/);
    expect(echo).toBeInTheDocument();
    expect(echo.textContent).not.toContain('取下滚刷');
    expect(screen.getByText('取下滚刷并剪掉缠绕的毛发。')).toBeInTheDocument();
  });

  it('没有 seen 时不渲染空行', () => {
    const { container } = render(<StepCard item={base} active onFeedback={vi.fn()} />);
    expect(container.querySelector('[data-kind="vision-echo"]')).toBeNull();
  });
});
