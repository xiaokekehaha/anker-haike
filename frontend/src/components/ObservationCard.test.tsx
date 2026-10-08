import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ObservationCardItem } from '../types/snapshot';
import { ObservationCard } from './ObservationCard';

const OBSERVATION: ObservationCardItem['observation'] = {
  observation_id: 'station_display',
  question: '放回基站后，App 里显示更接近下面哪种情况？',
  options: [
    { option_id: 'error_7033', label: '提示 7033 回不了基站', kind: 'finding' },
    { option_id: 'abnormal', label: '显示充电中但电量不涨', kind: 'finding' },
    { option_id: 'unknown', label: '设备不在身边或无法判断', kind: 'unknown' },
  ],
};
const item = (over: Partial<ObservationCardItem> = {}): ObservationCardItem => ({
  kind: 'observation_card', card_id: 'k1', version: 1, observation: OBSERVATION, plan_id: 'qa_rv_0101', attempt: 1, chosen_option_id: null, ...over,
});

describe('ObservationCard', () => {
  it('每个选项点一次即提交，unknown 与现象选项分开', () => {
    const onAnswer = vi.fn();
    const { container } = render(<ObservationCard item={item()} active onAnswer={onAnswer} />);
    // 快捷回复 chip 紧跟问题，卡片头复述问题本身，不再有「选择最接近的情况」这类模板标题
    expect(screen.getByText('放回基站后，App 里显示更接近下面哪种情况？')).toBeVisible();
    expect(screen.queryByText('选择最接近的情况')).toBeNull();
    // unknown 不在候选网格里：它是「答不上来」，不是一种现象
    expect(container.querySelectorAll('ul button')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '提示 7033 回不了基站' }));
    expect(onAnswer).toHaveBeenCalledWith('station_display', 'error_7033');
    fireEvent.click(screen.getByRole('button', { name: '设备不在身边或无法判断' }));
    expect(onAnswer).toHaveBeenLastCalledWith('station_display', 'unknown');
  });

  it('只有 active 卡可点；已回答的旧卡折叠成一行', () => {
    const onAnswer = vi.fn();
    const { container } = render(
      <>
        <ObservationCard item={item({ card_id: 'old', chosen_option_id: 'abnormal' })} active={false} onAnswer={onAnswer} />
        <ObservationCard item={item({ card_id: 'cur' })} active onAnswer={onAnswer} />
      </>,
    );
    const cards = container.querySelectorAll('[data-kind="observation_card"]');
    expect(cards).toHaveLength(2);
    expect(cards[0]!).toHaveTextContent('显示充电中但电量不涨');
    expect(cards[0]!.querySelectorAll('button')).toHaveLength(0);
    expect(screen.getAllByRole('button', { name: '提示 7033 回不了基站' })).toHaveLength(1);
  });

  it('动作进行中或已选择后不再可点', () => {
    const onAnswer = vi.fn();
    const { rerender } = render(<ObservationCard item={item()} active disabled onAnswer={onAnswer} />);
    expect(screen.getByRole('button', { name: '提示 7033 回不了基站' })).toBeDisabled();
    rerender(<ObservationCard item={item({ chosen_option_id: 'laptop_uvp' })} active onAnswer={onAnswer} />);
    expect(screen.getByRole('button', { name: '提示 7033 回不了基站' })).toBeDisabled();
    expect(screen.getByText('已选择')).toBeVisible();
  });
});
