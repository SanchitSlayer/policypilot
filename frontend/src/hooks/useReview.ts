"use client";

import { useEffect, useState } from "react";

import { getReview } from "@/lib/api";
import type { ReviewOut } from "@/lib/types";

const POLL_MS = 1500;

/** Loads a review and polls it while the agent is still running. */
export function useReview(reviewId: string | null) {
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reviewId) {
      setReview(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const next = await getReview(reviewId);
        if (cancelled) return;
        setReview(next);
        setError(null);
        if (next.status === "running") timer = setTimeout(load, POLL_MS);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load the review.");
        timer = setTimeout(load, POLL_MS * 2);
      }
    };

    setReview(null);
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [reviewId]);

  return { review, error };
}
