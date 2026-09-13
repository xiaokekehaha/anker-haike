import { describe, expect, it } from 'vitest';
import { parseFrame, readSSE } from './sse';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
}

describe('SSE parser (票 06)', () => {
  it('splits frames on blank lines, joins multi-line data and tolerates chunk boundaries', async () => {
    const got: string[] = [];
    await readSSE(
      streamOf(['id: 1\nevent: run_started\ndata: {"type":"run_started","seq":1,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z","resumed":false,', '"deadline_ms":25000}\n\nid: 2\nevent: ping\ndata: {"type":"ping",\ndata: "seq":2,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z"}\n\n']),
      (e) => { got.push(e.type); },
    );
    expect(got).toEqual(['run_started', 'ping']);
  });
  it('drops invalid frames instead of throwing', () => {
    expect(parseFrame('data: {"type":"nope","seq":1,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z"}')).toBeNull();
    expect(parseFrame('data: not json')).toBeNull();
    expect(parseFrame(': comment only')).toBeNull();
  });
});

it('parses CRLF and CR even when split across chunks', async () => {
  const got: number[] = [];
  await readSSE(streamOf(['data: {"type":"ping","seq":1,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z"}\r', '\n\r', '\ndata: {"type":"ping","seq":2,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z"}\r\r']), e => { got.push(e.seq); });
  expect(got).toEqual([1, 2]);
});

it('does not dispatch a partial frame at EOF and releases the reader', async () => {
  const body = streamOf(['data: {"type":"ping","seq":1,"run_id":"r","event_id":"e","recorded_at":"2026-09-13T00:00:00Z"}']);
  const got: number[] = [];
  await readSSE(body, e => { got.push(e.seq); });
  expect(got).toEqual([]);
  expect(body.locked).toBe(false);
});

it('cancels a pending read and supports an already aborted signal', async () => {
  for (const alreadyAborted of [true, false]) {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
    const controller = new AbortController();
    if (alreadyAborted) controller.abort();
    const reading = readSSE(body, () => { throw new Error('late event'); }, controller.signal);
    controller.abort();
    await reading;
    expect(cancelled).toBe(true);
    expect(body.locked).toBe(false);
  }
});
