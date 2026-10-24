import { readSSEStream } from "./sse";
import type {
  ChatRequest,
  ChatResponse,
  CitationsEvent,
  ConversationDetail,
  ConversationSummary,
  DocType,
  DocumentDetail,
  DocumentOut,
  DoneEvent,
  ErrorEvent,
  ReviewCreated,
  ReviewOut,
  ReviewRequest,
  TokenEvent,
  UsageSummary,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 20);

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI errors are {"detail": string} or {"detail": [{msg, loc}]} (validation). */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) =>
        [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  return status === 0 ? "Cannot reach the PolicyPilot API." : `Request failed (HTTP ${status}).`;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, errorMessage(0, null));
  }
  const body = await parseBody(response);
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body));
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// --- Documents --------------------------------------------------------------------------

export const listDocuments = () => request<DocumentOut[]>("/documents");

export const getDocument = (id: string) => request<DocumentDetail>(`/documents/${id}`);

export const deleteDocument = (id: string) =>
  request<null>(`/documents/${id}`, { method: "DELETE" });

/** Upload with progress (fetch cannot report upload progress, so this uses XHR). */
export function uploadDocument(
  file: File,
  docType: DocType,
  onProgress?: (fraction: number) => void,
): Promise<DocumentOut> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/documents`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = { detail: xhr.responseText };
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as DocumentOut);
      else reject(new ApiError(xhr.status, errorMessage(xhr.status, body)));
    };
    xhr.onerror = () => reject(new ApiError(0, errorMessage(0, null)));
    xhr.send(form);
  });
}

// --- Chat ---------------------------------------------------------------------------------

export const chat = (body: ChatRequest) => request<ChatResponse>("/chat", json(body));

export interface StreamHandlers {
  onToken: (text: string) => void;
  onCitations?: (event: CitationsEvent) => void;
  onDone?: (event: DoneEvent) => void;
}

/**
 * POST /chat/stream and dispatch its Server-Sent Events. Resolves when the stream ends.
 * Throws ApiError for HTTP errors and for an `error` event; abort via `signal`.
 */
export async function streamChat(
  body: ChatRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/chat/stream`, { ...json(body), signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, errorMessage(0, null));
  }
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, errorMessage(response.status, await parseBody(response)));
  }

  let streamError: string | null = null;
  await readSSEStream(response.body, ({ event, data }) => {
    const payload: unknown = JSON.parse(data);
    if (event === "token") handlers.onToken((payload as TokenEvent).text);
    else if (event === "citations") handlers.onCitations?.(payload as CitationsEvent);
    else if (event === "done") handlers.onDone?.(payload as DoneEvent);
    else if (event === "error") streamError = (payload as ErrorEvent).detail;
  });
  if (streamError) throw new ApiError(502, streamError);
}

// --- Contract review ----------------------------------------------------------------------

export const startReview = (body: ReviewRequest) => request<ReviewCreated>("/review", json(body));

export const getReview = (id: string) => request<ReviewOut>(`/review/${id}`);

// --- Conversation history -----------------------------------------------------------------

export const listConversations = () => request<ConversationSummary[]>("/conversations");

export const getConversation = (id: string) =>
  request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`);

export const deleteConversation = (id: string) =>
  request<null>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });

// --- Admin --------------------------------------------------------------------------------

export const getUsage = (from: string, to: string) =>
  request<UsageSummary>(`/admin/usage?${new URLSearchParams({ from, to })}`);
