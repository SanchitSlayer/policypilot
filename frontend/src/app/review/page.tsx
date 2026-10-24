"use client";

import { FileWarning, Play } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { ProviderSelect } from "@/components/chat/ChatControls";
import { PageHeader } from "@/components/PageHeader";
import { AgentProgress } from "@/components/review/AgentProgress";
import { FindingsTable } from "@/components/review/FindingsTable";
import { ReportSummary } from "@/components/review/ReportSummary";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useDocuments } from "@/hooks/useDocuments";
import { useReview } from "@/hooks/useReview";
import { useStoredProvider } from "@/hooks/useStoredProvider";
import { startReview } from "@/lib/api";

export default function ReviewPage() {
  return (
    <Suspense>
      <ContractReview />
    </Suspense>
  );
}

function ContractReview() {
  const router = useRouter();
  const reviewId = useSearchParams().get("review");
  const [provider, setProvider] = useStoredProvider();
  const { documents, loading } = useDocuments();
  const contracts = useMemo(
    () => documents.filter((d) => d.doc_type === "contract" && d.status === "ready"),
    [documents],
  );
  const [selected, setSelected] = useState("");
  const contractId = selected || contracts[0]?.id || "";

  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const { review, error: loadError } = useReview(reviewId);
  const running = starting || review?.status === "running";

  const run = async () => {
    if (!contractId) return;
    setStarting(true);
    setStartError(null);
    try {
      const created = await startReview({ document_id: contractId, provider });
      router.replace(`/review?review=${created.review_id}`);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Could not start the review.");
    } finally {
      setStarting(false);
    }
  };

  const listed = review?.steps.find((s) => s.tool === "list_contract_clauses" && s.ok);
  const totalClauses = listed ? Number(listed.description.match(/(\d+) clauses/)?.[1] ?? 0) : null;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Contract Review"
        description="An AI agent checks every clause of a contract against your stored policies and cites the rules it applied."
      />

      <section aria-label="Start a review" className="mb-6 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
        {!loading && contracts.length === 0 ? (
          <div className="flex items-start gap-3 text-sm text-slate-600">
            <FileWarning aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
            <p>
              No contracts yet.{" "}
              <Link href="/documents" className="font-medium text-indigo-600 hover:underline">
                Upload a PDF on the Documents page
              </Link>{" "}
              with type <span className="font-medium">Contract</span>, plus the policies to check it against.
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex w-full flex-col gap-1 text-sm text-slate-600 sm:w-auto sm:min-w-[280px] sm:flex-1">
              Contract
              <select
                value={contractId}
                onChange={(e) => setSelected(e.target.value)}
                disabled={running || loading}
                className="h-9 rounded-md border border-slate-300 bg-white px-2.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              >
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </label>
            <ProviderSelect value={provider} onChange={setProvider} disabled={running} />
            <button
              type="button"
              onClick={() => void run()}
              disabled={!contractId || running}
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-indigo-600 px-3.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Play aria-hidden className="h-4 w-4" />
              {running ? "Reviewing…" : "Run review"}
            </button>
          </div>
        )}
      </section>

      {(startError || loadError) && (
        <div className="mb-6">
          <ErrorBanner message={startError ?? loadError ?? ""} />
        </div>
      )}

      {review && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold text-slate-900">{review.contract_title}</h2>
            <span className="text-xs text-slate-500">
              Started {new Date(review.created_at).toLocaleString()}
            </span>
          </div>

          {review.status === "failed" && (
            <ErrorBanner message={`The review failed: ${review.message ?? "unknown error"}`} />
          )}
          {review.report && <ReportSummary report={review.report} />}

          <div className={review.report ? "" : "grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]"}>
            {!review.report && (
              <div className="order-2 lg:order-1">
                {review.findings.length > 0 ? (
                  <FindingsTable findings={review.findings} />
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                    Findings appear here as the agent records them.
                  </div>
                )}
              </div>
            )}
            <div className={review.report ? "hidden" : "order-1 lg:order-2"}>
              <AgentProgress
                steps={review.steps}
                running={review.status === "running"}
                reviewed={review.findings.length}
                total={totalClauses}
              />
            </div>
          </div>

          {review.report && (
            <>
              <FindingsTable findings={review.report.findings} />
              <details className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
                <summary className="cursor-pointer font-medium text-slate-700">
                  Agent activity ({review.steps.length} actions)
                </summary>
                <div className="mt-3">
                  <AgentProgress steps={review.steps} running={false} reviewed={review.findings.length} total={totalClauses} />
                </div>
              </details>
            </>
          )}
        </div>
      )}
    </div>
  );
}
