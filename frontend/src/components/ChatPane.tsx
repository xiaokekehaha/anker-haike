import type { ReactNode } from 'react';
import styles from './ChatPane.module.css';

export const PRODUCT_CATEGORIES = [
  { key: 'robot_vacuum', label: '扫地机器人', icon: '🤖' },
  { key: 'breast_pump', label: '吸奶器', icon: '🍼' },
  { key: 'charging', label: '充电与移动电源', icon: '🔋' },
  { key: 'audio', label: '耳机与音箱', icon: '🎧' },
  { key: 'security', label: '安防摄像头', icon: '📷' },
  { key: 'projector', label: '投影仪', icon: '📽️' },
] as const;

export const STARTER_PROMPTS = [
  { text: '我的 S1 Pro 不吸了，明天家里要来客人，急！', tag: '故障描述' },
  { text: '充电宝充不进电，指示灯一直在闪', tag: '故障描述' },
  { text: '耳机只有一边有声音，重置过还是不行', tag: '故障描述' },
  { text: '我在经销商那里买的，订单查不到，还能保修吗', tag: '订单与售后' },
] as const;

type Props = { onPick: (text: string) => void; disabled?: boolean; children?: ReactNode };

export function ChatPane({ onPick, disabled, children }: Props) {
  return (
    <div className={styles.pane}>
      <div className={styles.assistant}>
        <span className={styles.avatar} aria-hidden="true">✦</span>
        <div className={styles.bubble}>
          <p>你好，我是 Anker 智能售后助手。说说你的设备遇到了什么问题，我会陪你一步步排查。</p>
        </div>
      </div>

      {children}

      <section className={styles.block} aria-labelledby="cat-title">
        <h3 id="cat-title">也可以先选产品<span>选填</span></h3>
        <ul className={styles.categories}>
          {PRODUCT_CATEGORIES.map((c) => (
            <li key={c.key}>
              <button type="button" disabled={disabled} onClick={() => onPick(`我的${c.label}出问题了：`)}>
                <span aria-hidden="true">{c.icon}</span>{c.label}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <details className={styles.examples}>
        <summary>不知道怎么说？看看示例</summary>
        <ul className={styles.starters}>
          {STARTER_PROMPTS.map((s) => (
            <li key={s.text}>
              <button type="button" disabled={disabled} onClick={() => onPick(s.text)}>
                <span className={styles.starterTag}>{s.tag}</span>
                <span>{s.text}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
