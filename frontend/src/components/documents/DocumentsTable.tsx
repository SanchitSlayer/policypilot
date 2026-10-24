"use client";

import { FileText, Trash2 } from "lucide-react";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DocumentOut } from "@/lib/types";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

type DocumentsTableProps = {
  documents: DocumentOut[];
  onDelete: (document: DocumentOut) => void;
};

export function DocumentsTable({ documents, onDelete }: DocumentsTableProps) {
  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
        <FileText aria-hidden className="mx-auto h-8 w-8 text-slate-300" />
        <p className="mt-3 text-sm font-medium text-slate-700">No documents yet</p>
        <p className="mt-1 text-sm text-slate-500">
          Upload a policy PDF above, such as the RBI KYC Master Direction.
        </p>
      </div>
    );
  }

  return (
    <div className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-4 py-3">Title</th>
            <th scope="col" className="px-4 py-3">Type</th>
            <th scope="col" className="px-4 py-3 text-right">Pages</th>
            <th scope="col" className="px-4 py-3 text-right">Chunks</th>
            <th scope="col" className="px-4 py-3">Status</th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">Added</th>
            <th scope="col" className="px-4 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.map((doc) => (
            <tr key={doc.id} className="hover:bg-slate-50/60">
              <td className="max-w-xs px-4 py-3">
                <p className="truncate font-medium text-slate-900" title={doc.title}>
                  {doc.title}
                </p>
                <p className="truncate text-xs text-slate-500" title={doc.filename}>
                  {doc.filename}
                </p>
                {doc.status === "failed" && doc.error_message && (
                  <p className="mt-1 text-xs text-rose-600">{doc.error_message}</p>
                )}
              </td>
              <td className="px-4 py-3 capitalize text-slate-600">{doc.doc_type}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-600">{doc.num_pages ?? "—"}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                {doc.status === "ready" ? doc.chunk_count : "—"}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={doc.status} title={doc.error_message ?? undefined} />
              </td>
              <td className="hidden whitespace-nowrap px-4 py-3 text-slate-500 md:table-cell">
                {dateFormat.format(new Date(doc.created_at))}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => onDelete(doc)}
                  aria-label={`Delete ${doc.title}`}
                  className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 focus-visible:outline-2 focus-visible:outline-rose-600"
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
