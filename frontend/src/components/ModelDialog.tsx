import { useEffect, useRef, useState } from 'react';
import { fetchModels, probeModel, type ModelList, type ModelStatus } from '../api/models';
import styles from './ModelDialog.module.css';

const STATUS = { unconfigured: '未配置', unchecked: '未检测', checking: '检测中', connected: '已连通', failed: '连接失败' };
const LANE: Record<string, string> = { domestic: '国内', overseas: '海外', zhipu: '智谱优先' };
const PROVIDER: Record<string, string> = { deepseek: 'DeepSeek', zhipu: '智谱', dashscope: '通义千问', anthropic: 'Anthropic', google: 'Google' };

export function ModelDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const alive = useRef(false);
  const controllers = useRef(new Set<AbortController>());
  const activeAliases = useRef(new Set<string>());
  const loadRevision = useRef(0);
  const [data, setData] = useState<ModelList | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(new Set<string>());
  const [batch, setBatch] = useState(false);

  function close() {
    // 先解除原生 modal 的背景 inert，再由入口恢复键盘焦点。
    dialog.current?.close();
    onClose();
  }

  async function load() {
    const revision = ++loadRevision.current;
    const controller = new AbortController();
    controllers.current.add(controller);
    const timeout = setTimeout(() => controller.abort(), 5_000);
    try {
      const next = await fetchModels(controller.signal);
      if (alive.current && revision === loadRevision.current && !controller.signal.aborted) { setData(next); setLoadError(null); }
    } catch {
      if (alive.current && revision === loadRevision.current) setLoadError('暂时无法获取模型列表，请重试');
    } finally {
      clearTimeout(timeout);
      controllers.current.delete(controller);
      if (alive.current && revision === loadRevision.current) setLoading(false);
    }
  }

  useEffect(() => {
    alive.current = true;
    const element = dialog.current!;
    element.showModal();
    void load();
    const requests = controllers.current;
    return () => {
      alive.current = false;
      loadRevision.current++;
      requests.forEach((controller) => controller.abort());
      requests.clear();
      element.close();
    };
  }, []);

  // 重开弹窗时，若服务端尚有探测进行，只轮询结果，不发起模型调用。
  useEffect(() => {
    if (pending.size || !data?.models.some((model) => model.status === 'checking')) return;
    const timer = setTimeout(() => void load(), 1_000);
    return () => clearTimeout(timer);
  }, [data, pending]);

  useEffect(() => {
    const expiries = data?.models.filter((model) => ['connected', 'failed'].includes(model.status) && model.expires_at)
      .map((model) => Date.parse(model.expires_at!)) ?? [];
    if (!expiries.length) return;
    const timer = setTimeout(() => setData((current) => current && ({ ...current, models: current.models.map((model) =>
      ['connected', 'failed'].includes(model.status) && model.expires_at && Date.parse(model.expires_at) <= Date.now()
        ? { ...model, status: 'unchecked', detail: '上次检测已过期，请重新检测', latency_ms: null } : model,
    ) })), Math.max(0, Math.min(...expiries) - Date.now()) + 10);
    return () => clearTimeout(timer);
  }, [data]);

  async function check(alias: string) {
    if (activeAliases.current.has(alias)) return;
    activeAliases.current.add(alias);
    loadRevision.current++;
    setPending(new Set(activeAliases.current));
    setErrors((current) => { const next = { ...current }; delete next[alias]; return next; });
    const controller = new AbortController();
    controllers.current.add(controller);
    const timeout = setTimeout(() => controller.abort(), 25_000);
    try {
      const result = await probeModel(alias, controller.signal);
      if (alive.current) setData((current) => current && ({ ...current, models: current.models.map((model) => model.alias === alias ? result : model) }));
    } catch (error) {
      if (alive.current) {
        setErrors((current) => ({ ...current, [alias]: error instanceof Error && error.name !== 'AbortError' && !(error instanceof TypeError)
          && error.name !== 'ZodError' ? error.message : '未能获取检测结果，请重试' }));
        // 检测请求失败不能继续展示旧绿灯，也不能判定厂商连接失败。
        setData((current) => current && ({ ...current, models: current.models.map((model) => model.alias === alias
          ? { ...model, status: 'unchecked', detail: null, latency_ms: null, checked_at: null, expires_at: null } : model) }));
      }
    } finally {
      clearTimeout(timeout);
      controllers.current.delete(controller);
      activeAliases.current.delete(alias);
      if (alive.current) setPending(new Set(activeAliases.current));
    }
  }

  async function checkCurrent() {
    if (batch || activeAliases.current.size || !data?.probe_enabled) return;
    const aliases = data.models.filter((model) => model.current_lane && model.configured).map((model) => model.alias);
    let index = 0;
    setBatch(true);
    async function worker() {
      while (alive.current && index < aliases.length) await check(aliases[index++]!);
    }
    await Promise.all([worker(), worker()]);
    if (alive.current) setBatch(false);
  }

  function rows(models: ModelStatus[]) {
    return <ul className={styles.models}>{models.map((model) => {
      const checking = pending.has(model.alias) || model.status === 'checking';
      const status = checking ? 'checking' : model.status;
      return <li key={model.alias} className={styles.model} aria-label={`${model.alias} 模型`}>
        <div className={styles.identity}>
          <strong>{model.model_id}</strong>
          <span>{PROVIDER[model.provider] ?? model.provider} · {model.alias}</span>
        </div>
        <div className={styles.result} aria-live="polite">
          <span className={styles.status} data-status={status}><i aria-hidden="true" />{STATUS[status]}</span>
          {!checking && model.detail && <span className={styles.detail}>{model.detail}</span>}
          {!checking && model.checked_at && <span className={styles.time}>
            {model.latency_ms !== null && `${model.latency_ms} ms · `}
            {new Date(model.checked_at).toLocaleTimeString('zh-CN', { hour12: false })} 检测
          </span>}
          {errors[model.alias] && <span className={styles.error} role="alert">{errors[model.alias]}</span>}
        </div>
        <button className={styles.check} disabled={!model.configured || !data?.probe_enabled || batch || pending.size > 0}
          onClick={() => void check(model.alias)} aria-label={`检测 ${model.alias}`}>
          {checking ? '检测中…' : model.checked_at ? '重测' : '检测'}
        </button>
      </li>;
    })}</ul>;
  }

  const current = data?.models.filter((model) => model.current_lane) ?? [];
  const other = data?.models.filter((model) => !model.current_lane) ?? [];
  return <dialog ref={dialog} className={styles.dialog} aria-labelledby="models-title" aria-describedby="models-description"
    onCancel={(event) => { event.preventDefault(); close(); }}>
    <div className={styles.heading}>
      <div><p className={styles.eyebrow}>模型连接</p><h2 id="models-title">哪些模型可以连通</h2></div>
      <button className={styles.close} onClick={close} aria-label="关闭模型列表" autoFocus>×</button>
    </div>
    <p id="models-description" className={styles.description}>点击检测会发送一次简短消息。结果保留 5 分钟，仅验证基础对话，不代表图片识别等功能已通过。</p>
    {loadError && <p className={styles.loadError} role="alert">{loadError}<button onClick={() => void load()}>重新加载</button></p>}
    {loading && <p className={styles.loading} role="status">正在读取模型列表…</p>}
    {data && <>
      {data.disabled_reason && <p className={styles.notice}>{data.disabled_reason}</p>}
      <div className={styles.toolbar}>
        <h3>当前通道 · {LANE[data.lane] ?? data.lane}<span>{current.length} 个模型</span></h3>
        <button className={styles.primary} onClick={() => void checkCurrent()}
          disabled={!data.probe_enabled || batch || pending.size > 0 || !current.some((model) => model.configured)}>
          {batch ? '正在检测…' : '检测已配置模型'}
        </button>
      </div>
      <p className={styles.hint}>批量检测当前通道，未配置的模型自动跳过。</p>
      {current.length ? rows(current) : <p className={styles.loading}>当前通道没有聊天模型</p>}
      {other.length > 0 && <details className={styles.other}><summary>其他模型 <span>{other.length}</span></summary>{rows(other)}</details>}
    </>}
  </dialog>;
}
