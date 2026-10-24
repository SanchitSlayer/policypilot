"use client";

import { useCallback, useEffect, useState } from "react";

import { deleteConversation, listConversations } from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await listConversations());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await deleteConversation(id);
    setConversations((current) => current.filter((c) => c.conversation_id !== id));
  }, []);

  return { conversations, loading, error, refresh, remove };
}
