"use client";

import { useCallback, useEffect, useState } from "react";

import { listDocuments } from "@/lib/api";
import type { DocumentOut } from "@/lib/types";

const POLL_MS = 2000;

/** Loads the document list and polls while any document is still processing. */
export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const processing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [processing, refresh]);

  return { documents, loading, error, refresh };
}
