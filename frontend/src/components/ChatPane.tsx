import styles from './ChatPane.module.css';

// 品类键与文案对齐 config/products.yaml（官网五大产品线下的品类）；点击发出的文字要能被 category_hint 的关键词认出。
// supported = config/plans.yaml 里已有排障计划的品类；其余品类在首屏置灰，等资料补齐后翻成 true 即可。
export const PRODUCT_CATEGORIES = [
  { key: 'power_bank', label: '移动电源', supported: true },
  { key: 'charger', label: '充电器', supported: true },
  { key: 'robot_vacuum', label: '扫地机器人', supported: true },
  { key: 'security_cam', label: '安防摄像头', supported: true },
  { key: 'breast_pump', label: '吸奶器', supported: true },
  { key: 'earbuds', label: '无线耳机', supported: true },
  { key: 'headphones', label: '头戴式耳机', supported: true },
  { key: 'speaker', label: '音箱', supported: true },
  { key: 'cable', label: '数据线', supported: false },
  { key: 'wireless_charger', label: '无线充电器', supported: false },
  { key: 'charging_station', label: '充电站', supported: false },
  { key: 'hub', label: '集线器与拓展坞', supported: false },
  { key: 'portable_power_station', label: '便携储能', supported: false },
  { key: 'robot_mower', label: '割草机器人', supported: false },
  { key: 'baby_monitor', label: '婴儿监视器', supported: false },
  { key: 'smart_scale', label: '智能体重秤', supported: false },
  { key: 'sleep_earbuds', label: '睡眠耳机', supported: false },
  { key: 'projector', label: '便携投影仪', supported: false },
  { key: 'uv_printer', label: 'UV 打印机', supported: false },
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
        <h3 id="cat-title">也可以先选产品<span>选填</span><em>灰色品类的排障资料还在整理，可以直接描述问题</em></h3>
        <ul className={styles.categories}>
          {PRODUCT_CATEGORIES.map((c) => (
            <li key={c.key}>
              <button type="button" disabled={disabled || !c.supported} data-supported={c.supported || undefined}
                title={c.supported ? undefined : '排障资料整理中，暂不支持自助排查'} aria-label={c.supported ? undefined : `${c.label}（暂不支持）`}
                onClick={() => onPick(`我的${c.label}出问题了：`)}>{c.label}</button>
            </li>
          ))}
        </ul>
      </section>

      <details className={styles.examples} open>
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
