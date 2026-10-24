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

// Contract review (POST /review, GET /review/{id})

export type ReviewStatus = "running" | "completed" | "failed";
export type FindingStatus = "compliant" | "non_compliant" | "needs_review";
export type OverallRisk = "low" | "medium" | "high";

export interface ReviewRequest {
  document_id: string;
  provider?: ProviderName;
}

export interface ReviewCreated {
  review_id: string;
  status: ReviewStatus;
}

export interface PolicyCitation {
  source_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  snippet: string;
}

export interface FindingOut {
  clause_id: string;
  clause_title: string;
  clause_page: number | null;
  status: FindingStatus;
  reason: string;
  policy_citations: PolicyCitation[];
}

export interface ReviewStep {
  index: number;
  tool: string;
  description: string;
  ok: boolean;
  at: string;
}

export interface ReviewReport {
  contract_id: string;
  contract_title: string;
  provider: string;
  model: string | null;
  summary: string;
  overall_risk: OverallRisk;
  findings: FindingOut[];
  steps_used: number;
  tokens_used: number;
  message: string | null;
  prompt_version: string | null;
}

export interface ReviewOut {
  id: string;
  contract_id: string;
  contract_title: string;
  provider: string;
  status: ReviewStatus;
  steps: ReviewStep[];
  findings: FindingOut[];
  steps_used: number;
  tokens_used: number;
  message: string | null;
  created_at: string;
  completed_at: string | null;
  report: ReviewReport | null;
}
