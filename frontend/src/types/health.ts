// /health 是运维接口；会话事件的生成类型由票 04 单独接入。
export type ComponentStatus = 'ok' | 'down' | 'unconfigured';

export type ComponentHealth = { status: ComponentStatus };

export type HealthSnapshot = {
  status: 'ok' | 'degraded';
  lane: string;
  components: {
    db: ComponentHealth;
    weknora: ComponentHealth;
    models: Record<string, ComponentHealth>;
  };
};

export type HealthState = {
  snapshot: HealthSnapshot | null;
  error: string | null;
  checkedAt: Date | null;
  refreshing: boolean;
};
