import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, errorMessage, streamChat } from "./api";

function sseResponse(body: string, status = 200): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const bytes = new TextEncoder().encode(body);
      controller.enqueue(bytes.slice(0, 40));
      controller.enqueue(bytes.slice(40));
      controller.close();
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "text/event-stream" } });
}

const CITATION = {
  source: 1,
  chunk_id: "c1",
  document_id: "d1",
  document_title: "KYC Direction",
  page_number: 12,
  snippet: "Passport…",
};

afterEach(() => vi.unstubAllGlobals());

describe("streamChat", () => {
  it("dispatches token, citations and done events in order", async () => {
    const body =
      'event: token\ndata: {"text":"Passport "}\n\n' +
      'event: token\ndata: {"text":"[1]"}\n\n' +
      `event: citations\ndata: ${JSON.stringify({ conversation_id: "abc", citations: [CITATION], sources: [] })}\n\n` +
      'event: done\ndata: {"conversation_id":"abc","answer":"Passport [1]","usage":{"provider":"fake","model":"m","input_tokens":1,"output_tokens":2,"latency_ms":3},"prompt_version":"rag-v1"}\n\n';
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(body));
    vi.stubGlobal("fetch", fetchMock);
    const calls: string[] = [];

    await streamChat(
      { question: "q", provider: "fake" },
      {
        onToken: (t) => calls.push(`token:${t}`),
        onCitations: (e) => calls.push(`citations:${e.citations[0].page_number}`),
        onDone: (e) => calls.push(`done:${e.answer}`),
      },
    );

    expect(calls).toEqual(["token:Passport ", "token:[1]", "citations:12", "done:Passport [1]"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/chat\/stream$/);
    expect(JSON.parse(init.body)).toEqual({ question: "q", provider: "fake" });
  });

  it("throws the API's error detail for HTTP errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Provider 'openai' is not configured" }), { status: 400 }),
      ),
    );

    await expect(streamChat({ question: "q" }, { onToken: () => {} })).rejects.toEqual(
      new ApiError(400, "Provider 'openai' is not configured"),
    );
  });

  it("throws when the stream reports an error event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(sseResponse('event: token\ndata: {"text":"x"}\n\nevent: error\ndata: {"detail":"rate limited"}\n\n')),
    );

    await expect(streamChat({ question: "q" }, { onToken: () => {} })).rejects.toThrow("rate limited");
  });
});

describe("errorMessage", () => {
  it("formats FastAPI validation errors", () => {
    const body = { detail: [{ loc: ["body", "question"], msg: "String should have at least 1 character" }] };
    expect(errorMessage(422, body)).toBe("question: String should have at least 1 character");
  });

  it("explains network failures", () => {
    expect(errorMessage(0, null)).toBe("Cannot reach the PolicyPilot API.");
  });
});
