/** Context estimates are distinct from provider-reported input usage. */
const BLOCK_NAMES: Record<string, string> = {
  system: '系统指令', authority: '状态事实', current: '本轮输入', history: '历史原文',
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function tokens(value: unknown): string {
  return typeof value === 'number' ? value.toLocaleString('en-US') : '—';
}

export function ContextMetrics({ value }: { value: unknown }) {
  if (!Array.isArray(value)) return null;
  return <section aria-label="上下文预算">
    <h3>上下文预算</h3>
    {value.map((item: unknown, index) => {
      const metric = record(item);
      if (!metric) return null;
      if (metric.event === 'model_call') {
        const attempts = Array.isArray(metric.attempts) ? metric.attempts : [];
        return <div key={index}>
          <p>实际输入 {tokens(metric.actual_input_tokens)} tok · {String(metric.model ?? '未调用模型')}</p>
          {attempts.map((attempt: unknown, attemptIndex) => {
            const a = record(attempt);
            return a && <p key={attemptIndex} className="mono">
              {String(a.alias)} · 估算输入（含 Schema）{tokens(a.estimated_input_tokens)} / {tokens(a.input_budget)} tok · {String(a.outcome)}
            </p>;
          })}
        </div>;
      }
      const blocks = record(metric.token_breakdown) ?? {};
      return <div key={index}>
        <p>{String(metric.task ?? '')} · {metric.event === 'context_budget' ? '必需内容超限' : '已装配'} · {tokens(metric.tokens ?? metric.required_tokens)} / {tokens(metric.max_tokens)} tok（已预留 Schema 等开销）</p>
        <dl>{Object.entries(blocks).map(([key, count]) => <div key={key}>
          <dt>{BLOCK_NAMES[key] ?? key}</dt><dd>{tokens(count)} tok</dd>
        </div>)}</dl>
        <p>未纳入历史 {tokens(metric.omitted_entries)} 条 · 本轮截断 {metric.truncated ? '是' : '否'} · 摘录缓存移除 {metric.cache_dropped ? '是' : '否'}</p>
      </div>;
    })}
  </section>;
}
