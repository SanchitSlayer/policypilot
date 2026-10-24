import { describe, expect, it } from "vitest";

import { createSSEParser, readSSEStream, type SSEMessage } from "./sse";

function collect(chunks: string[]): SSEMessage[] {
  const messages: SSEMessage[] = [];
  const parser = createSSEParser((m) => messages.push(m));
  chunks.forEach((c) => parser.feed(c));
  parser.end();
  return messages;
}

describe("createSSEParser", () => {
  it("parses named events with JSON data", () => {
    expect(collect(['event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n'])).toEqual([
      { event: "token", data: '{"text":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("reassembles events split across arbitrary chunk boundaries", () => {
    const raw = 'event: token\ndata: {"text":"Hello "}\n\nevent: token\ndata: {"text":"world"}\n\n';
    const split = raw.split(""); // one character per chunk
    expect(collect(split).map((m) => JSON.parse(m.data).text)).toEqual(["Hello ", "world"]);
  });

  it("handles CRLF line endings even when \\r and \\n arrive in different chunks", () => {
    expect(collect(["event: done\r", "\ndata: 1\r\n\r", "\n"])).toEqual([{ event: "done", data: "1" }]);
  });

  it("joins multi-line data, defaults the event name and ignores comments", () => {
    expect(collect([": keep-alive\n", "data: line one\ndata: line two\n\n"])).toEqual([
      { event: "message", data: "line one\nline two" },
    ]);
  });

  it("flushes a final event without a trailing blank line", () => {
    expect(collect(["event: done\ndata: {}"])).toEqual([{ event: "done", data: "{}" }]);
  });
});

describe("readSSEStream", () => {
  it("decodes a byte stream including multi-byte characters split across chunks", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"₹ 50,000"}\n\n');
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 30)); // splits the 3-byte ₹ character
        controller.enqueue(bytes.slice(30));
        controller.close();
      },
    });
    const messages: SSEMessage[] = [];

    await readSSEStream(stream, (m) => messages.push(m));

    expect(JSON.parse(messages[0].data).text).toBe("₹ 50,000");
  });
});
