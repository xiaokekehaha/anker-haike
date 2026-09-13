export function MessageTime({ at }: { at?: string | null }) {
  if (!at || Number.isNaN(Date.parse(at))) return null;
  const date = new Date(at);
  return <time dateTime={at} title={date.toLocaleString('zh-CN')} style={{ display: 'block', fontSize: 12, opacity: 0.65, marginTop: 6 }}>
    {date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
  </time>;
}
