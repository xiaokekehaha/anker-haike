import styles from './ChatPane.module.css';

// 品类键与文案对齐 config/products.yaml（官网五大产品线下的品类）；点击发出的文字要能被 category_hint 的关键词认出
export const PRODUCT_CATEGORIES = [
  { key: 'power_bank', label: '移动电源' },
  { key: 'charger', label: '充电器' },
  { key: 'robot_vacuum', label: '扫地机器人' },
  { key: 'security_cam', label: '安防摄像头' },
  { key: 'breast_pump', label: '吸奶器' },
  { key: 'earbuds', label: '无线耳机' },
  { key: 'speaker', label: '音箱' },
  { key: 'projector', label: '便携投影仪' },
] as const;

export const STARTER_PROMPTS = [
  { text: '我的 S1 Pro 不吸了，明天家里要来客人，急！', tag: '故障描述' },
  { text: '充电宝充不进电，指示灯一直在闪', tag: '故障描述' },
  { text: '耳机只有一边有声音，重置过还是不行', tag: '故障描述' },
  { text: '我在经销商那里买的，订单查不到，还能保修吗', tag: '订单与售后' },
] as const;

type Props = { onPick: (text: string) => void; disabled?: boolean };

/** 首屏 intake：一句开场白 + 品类 chip + 示例。线上 Live Chat 的开场白要求「一条消息里同时给型号与问题」，这里照做。 */
export function ChatPane({ onPick, disabled }: Props) {
  return (
    <div className={styles.pane}>
      <p className={styles.eyebrow}>ANKER 全线智能硬件 · 售后服务 · 真正听懂，真正解决</p>
      <div className={styles.assistant}>
        <span className={styles.avatar} aria-hidden="true">✦</span>
        <div className={styles.bubble}>
          <p>你好，我是 Anker 智能售后助手。一句话说说设备型号和遇到的问题，可以附上照片，我会陪你一步步排查。</p>
        </div>
      </div>

      <section className={styles.block} aria-labelledby="cat-title">
        <h3 id="cat-title">也可以先选产品<span>选填</span></h3>
        <ul className={styles.categories}>
          {PRODUCT_CATEGORIES.map((c) => (
            <li key={c.key}>
              <button type="button" disabled={disabled} onClick={() => onPick(`我的${c.label}出问题了：`)}>{c.label}</button>
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
