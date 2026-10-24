import { Loader2 } from "lucide-react";

import type { DocumentStatus } from "@/lib/types";

const STYLES: Record<DocumentStatus, string> = {
  processing: "bg-amber-50 text-amber-700 ring-amber-600/20",
  ready: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  failed: "bg-rose-50 text-rose-700 ring-rose-600/20",
};

const LABELS: Record<DocumentStatus, string> = {
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

export function StatusBadge({ status, title }: { status: DocumentStatus; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {status === "processing" && <Loader2 aria-hidden className="h-3 w-3 animate-spin" />}
      {LABELS[status]}
    </span>
  );
}
