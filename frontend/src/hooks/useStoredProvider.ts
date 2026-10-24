"use client";

import { useEffect, useState } from "react";

import { PROVIDERS } from "@/components/chat/ChatControls";
import type { ProviderName } from "@/lib/types";

const PROVIDER_KEY = "policypilot.provider";

/** The selected LLM provider, remembered across pages and visits (best effort). */
export function useStoredProvider(): [ProviderName, (provider: ProviderName) => void] {
  const [provider, setProvider] = useState<ProviderName>("openai");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(PROVIDER_KEY);
      if (PROVIDERS.some((p) => p.value === stored)) setProvider(stored as ProviderName);
    } catch {
      // storage unavailable (private mode); keep the default
    }
  }, []);

  const update = (next: ProviderName) => {
    setProvider(next);
    try {
      localStorage.setItem(PROVIDER_KEY, next);
    } catch {
      // ignore
    }
  };

  return [provider, update];
}
