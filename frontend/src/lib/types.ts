// Mirrors the backend Pydantic schemas (backend/app/schemas). Keep in sync.

export type DocType = "policy" | "contract";
export type DocumentStatus = "processing" | "ready" | "failed";
export type ProviderName = "openai" | "anthropic" | "gemini" | "fake";

export interface DocumentOut {
  id: string;
  filename: string;
  title: string;
  doc_type: DocType;
  num_pages: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  chunk_count: number;
}

export interface ChunkOut {
  id: string;
  chunk_index: number;
  page_number: number;
  token_count: number;
  content: string;
}

export interface DocumentDetail extends DocumentOut {
  chunks: ChunkOut[];
}

export interface ChatRequest {
  question: string;
  provider?: ProviderName;
  conversation_id?: string | null;
  document_ids?: string[] | null;
}

export interface Citation {
  source: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  snippet: string;
}

export interface SourceOut {
  number: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  score: number;
}

export interface ChatUsage {
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  sources: SourceOut[];
  usage: ChatUsage;
  prompt_version: string;
}

// Server-Sent Event payloads from POST /chat/stream
export interface TokenEvent {
  text: string;
}

export interface CitationsEvent {
  conversation_id: string;
  citations: Citation[];
  sources: SourceOut[];
}

export interface DoneEvent {
  conversation_id: string;
  answer: string;
  usage: ChatUsage;
  prompt_version: string;
}

export interface ErrorEvent {
  detail: string;
}
