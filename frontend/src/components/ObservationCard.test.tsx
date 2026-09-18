import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ObservationCardItem } from '../types/snapshot';
import { ObservationCard } from './ObservationCard';

const OBSERVATION: ObservationCardItem['observation'] = {
  observation_id: 'pb_737_display',
  question: '737 连接设备时，屏幕显示更接近下面哪种情况？',
  options: [
    { option_id: 'laptop_uvp', label: '连接笔记本时显示 UVP', kind: 'finding' },
    { option_id: 'abnormal', label: '屏幕显示异常或无法显示剩余电量', kind: 'finding' },
    { option_id: 'unknown', label: '设备不在身边或无法判断', kind: 'unknown' },
  ],
};
const item = (over: Partial<ObservationCardItem> = {}): ObservationCardItem => ({
  kind: 'observation_card', card_id: 'k1', version: 1, observation: OBSERVATION, plan_id: 'pb_737_output_check', attempt: 1, chosen_option_id: null, ...over,
});

describe('ObservationCard', () => {
  it('每个选项点一次即提交，unknown 与现象选项分开', () => {
    const onAnswer = vi.fn();
    const { container } = render(<ObservationCard item={item()} active onAnswer={onAnswer} />);
    // 问题由上一条助手消息问出，卡片头不重复
    expect(screen.queryByText('737 连接设备时，屏幕显示更接近下面哪种情况？')).toBeNull();
    expect(screen.getByText('选择最接近的情况')).toBeVisible();
    // unknown 不在候选网格里：它是「答不上来」，不是一种现象
    expect(container.querySelectorAll('ul button')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '连接笔记本时显示 UVP' }));
    expect(onAnswer).toHaveBeenCalledWith('pb_737_display', 'laptop_uvp');
    fireEvent.click(screen.getByRole('button', { name: '设备不在身边或无法判断' }));
    expect(onAnswer).toHaveBeenLastCalledWith('pb_737_display', 'unknown');
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
    expect(cards[0]!).toHaveTextContent('屏幕显示异常或无法显示剩余电量');
    expect(cards[0]!.querySelectorAll('button')).toHaveLength(0);
    expect(screen.getAllByRole('button', { name: '连接笔记本时显示 UVP' })).toHaveLength(1);
  });

  it('动作进行中或已选择后不再可点', () => {
    const onAnswer = vi.fn();
    const { rerender } = render(<ObservationCard item={item()} active disabled onAnswer={onAnswer} />);
    expect(screen.getByRole('button', { name: '连接笔记本时显示 UVP' })).toBeDisabled();
    rerender(<ObservationCard item={item({ chosen_option_id: 'laptop_uvp' })} active onAnswer={onAnswer} />);
    expect(screen.getByRole('button', { name: '连接笔记本时显示 UVP' })).toBeDisabled();
    expect(screen.getByText('已选择')).toBeVisible();
  });
});
