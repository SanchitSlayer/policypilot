"use client";

import { useState } from "react";

import { DocumentsTable } from "@/components/documents/DocumentsTable";
import { UploadDropzone } from "@/components/documents/UploadDropzone";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useDocuments } from "@/hooks/useDocuments";
import { deleteDocument } from "@/lib/api";
import type { DocumentOut } from "@/lib/types";

export default function DocumentsPage() {
  const { documents, loading, error, refresh } = useDocuments();
  const [pendingDelete, setPendingDelete] = useState<DocumentOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteDocument(pendingDelete.id);
      setDeleteError(null);
      await refresh();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not delete the document.");
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Documents"
        description="Upload policy and regulatory PDFs to build your knowledge base."
      />
      <div className="space-y-6">
        <UploadDropzone onUploaded={() => void refresh()} />
        {(error || deleteError) && <ErrorBanner message={error ?? deleteError ?? ""} onRetry={error ? refresh : undefined} />}
        {loading ? (
          <div className="h-40 animate-pulse rounded-xl bg-slate-200/60" aria-label="Loading documents" />
        ) : (
          <DocumentsTable documents={documents} onDelete={setPendingDelete} />
        )}
      </div>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete document?"
        description={
          <>
            <span className="font-medium text-slate-900">{pendingDelete?.title}</span> and all of its
            chunks will be removed. Answers will no longer cite it.
          </>
        }
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
