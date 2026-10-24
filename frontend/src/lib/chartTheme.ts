// Chart colours. Categorical slots come from the validated reference palette (light mode),
// assigned to providers in a fixed order so a provider keeps its colour on every chart and
// whatever subset of providers is in range. Validated: adjacent CVD ΔE >= 9.1, normal-vision
// ΔE >= 22.9. Gemini and Fake sit below 3:1 on the surface, so charts always carry a legend,
// direct labels where few marks, and the breakdown table below as the text alternative.

export const PROVIDER_ORDER = ["openai", "anthropic", "gemini", "fake"] as const;

export const PROVIDER_COLORS: Record<string, string> = {
  openai: "#2a78d6", // slot 1 blue
  anthropic: "#eb6834", // slot 2 orange
  gemini: "#1baf7a", // slot 3 aqua
  fake: "#eda100", // slot 4 yellow
};

export const OTHER_COLOR = "#898781";

export const providerColor = (provider: string) => PROVIDER_COLORS[provider] ?? OTHER_COLOR;

/** Sort providers by the fixed slot order, unknown ones last. */
export function orderProviders(providers: Iterable<string>): string[] {
  const rank = (p: string) => {
    const i = (PROVIDER_ORDER as readonly string[]).indexOf(p);
    return i === -1 ? PROVIDER_ORDER.length : i;
  };
  return [...new Set(providers)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

// Ordinal pair for p50 / p95 (one hue, light -> dark; validated as an ordinal ramp).
export const LATENCY_COLORS = { p50: "#86b6ef", p95: "#1c5cab" };

export const INK = {
  primary: "#0b0b0b",
  secondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  surface: "#ffffff",
};
