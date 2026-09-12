import { parseServerEvent } from './events';
import type { ServerEvent } from '../types/events';

/** 支持 SSE 的 LF / CRLF / CR、跨块 UTF-8 和多行 data；取消时丢弃未完成帧。 */
export async function readSSE(body: ReadableStream<Uint8Array>, onEvent: (e: ServerEvent) => void | boolean, signal?: AbortSignal): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lines: string[] = [];
  let afterCR = false;
  let stopped = false;
  const abort = () => void reader.cancel().catch(() => undefined);
  signal?.addEventListener('abort', abort, { once: true });
  function accept(text: string) {
    for (const char of text) {
      if (signal?.aborted || stopped) return;
      if (char === '\n' && afterCR) { afterCR = false; continue; }
      afterCR = char === '\r';
      if (char === '\r' || char === '\n') {
        if (buffer === '') {
          const event = parseFrame(lines.join('\n'));
          if (event && onEvent(event) === false) stopped = true;
          lines = [];
        } else lines.push(buffer);
        buffer = '';
      } else buffer += char;
    }
  }
  try {
    if (signal?.aborted) { await reader.cancel(); return; }
    for (;;) {
      const { value, done } = await reader.read();
      if (signal?.aborted || stopped) return;
      if (done) { accept(decoder.decode()); break; }
      accept(decoder.decode(value, { stream: true }));
      if (stopped) { await reader.cancel(); return; }
    }
    // SSE 只有空行才提交事件；断流留下的半帧等待服务端重放。
  } finally {
    signal?.removeEventListener('abort', abort);
    reader.releaseLock();
  }
}

export function parseFrame(raw: string): ServerEvent | null {
  const data = raw.split(/\r\n|\r|\n/)
    .filter((line) => line === 'data' || line.startsWith('data:'))
    .map((line) => line.slice(5).replace(/^ /, ''))
    .join('\n');
  if (!data) return null;
  try { return parseServerEvent(JSON.parse(data)); }
  catch { return null; }
}
