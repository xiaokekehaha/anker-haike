// /health 是运维接口；会话事件的生成类型由票 04 单独接入。
export type ComponentStatus = 'ok' | 'down' | 'unconfigured';

export type ComponentHealth = { status: ComponentStatus };

/** 票 43：只在后端 REPLAY_CASE_ID 设置时出现；down 表示录制包清单与当前版本不符。 */
export type ReplayHealth = { status: 'ok' | 'down'; caseId: string; title?: string };

export type HealthSnapshot = {
  status: 'ok' | 'degraded';
  lane: string;
  components: {
    db: ComponentHealth;
    weknora: ComponentHealth;
    models: Record<string, ComponentHealth>;
  };
  replay?: ReplayHealth;
};

export type HealthState = {
  snapshot: HealthSnapshot | null;
  error: string | null;
  checkedAt: Date | null;
  refreshing: boolean;
};
