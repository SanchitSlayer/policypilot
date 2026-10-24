export interface SSEMessage {
  event: string;
  data: string;
}

/**
 * Incremental Server-Sent Events parser. Feed it text as it arrives (chunks may split
 * events, lines or even "\r\n" pairs anywhere); it calls `onMessage` once per complete event.
 */
export function createSSEParser(onMessage: (message: SSEMessage) => void) {
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  const dispatch = () => {
    if (data.length > 0) onMessage({ event, data: data.join("\n") });
    event = "message";
    data = [];
  };

  const processLine = (line: string) => {
    if (line === "") return dispatch();
    if (line.startsWith(":")) return; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  };

  return {
    feed(chunk: string) {
      buffer += chunk;
      // Keep a trailing "\r" in the buffer: it may be the first half of "\r\n".
      const lines = buffer.split(/\r\n|\n|\r(?!$)/);
      buffer = lines.pop() ?? "";
      lines.forEach(processLine);
    },
    /** Flush a final event that was not followed by a blank line. */
    end() {
      if (buffer) processLine(buffer.replace(/\r$/, ""));
      buffer = "";
      dispatch();
    },
  };
}

/** Read a byte stream to the end, emitting parsed SSE messages. */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onMessage: (message: SSEMessage) => void,
): Promise<void> {
  const parser = createSSEParser(onMessage);
  const reader = body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    parser.feed(decoder.decode());
    parser.end();
  } finally {
    reader.releaseLock();
  }
}
