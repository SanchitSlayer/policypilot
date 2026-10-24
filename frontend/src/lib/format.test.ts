import { describe, expect, it } from "vitest";

import { timeAgo } from "@/components/chat/ConversationList";

import { orderProviders, providerColor } from "./chartTheme";
import { formatDay, formatMs, formatPct, formatUsd, presetRange } from "./format";

describe("formatters", () => {
  it("formats small costs with enough precision", () => {
    expect(formatUsd(0)).toBe("$0");
    expect(formatUsd(0.00042)).toBe("$0.0004");
    expect(formatUsd(1.234)).toBe("$1.23");
    expect(formatUsd(1234.5)).toMatch(/^\$1,?235$/);
  });

  it("formats latency and rates", () => {
    expect(formatMs(null)).toBe("—");
    expect(formatMs(412.4)).toBe("412 ms");
    expect(formatMs(2350)).toBe("2.4 s");
    expect(formatPct(0.2)).toBe("20.0%");
    expect(formatPct(0.004)).toBe("0.40%");
  });

  it("formats UTC days without shifting them by the local time zone", () => {
    expect(formatDay("2026-10-03")).toMatch(/Oct 3|3 Oct/);
  });
});

describe("presetRange", () => {
  it("covers the last N days inclusive", () => {
    expect(presetRange(7, new Date("2026-10-24T15:00:00Z"))).toEqual({ from: "2026-10-18", to: "2026-10-24" });
    expect(presetRange(1, new Date("2026-03-01T00:30:00Z"))).toEqual({ from: "2026-03-01", to: "2026-03-01" });
  });
});

describe("provider colours", () => {
  it("keep a fixed order and colour whatever subset is present", () => {
    expect(orderProviders(["fake", "gemini", "openai"])).toEqual(["openai", "gemini", "fake"]);
    expect(orderProviders(["mistral", "anthropic"])).toEqual(["anthropic", "mistral"]);
    expect(providerColor("gemini")).toBe("#1baf7a");
    expect(providerColor("mistral")).toBe("#898781");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-24T12:00:00Z").getTime();
  it("describes recent and older times", () => {
    expect(timeAgo("2026-10-24T11:59:40Z", now)).toBe("just now");
    expect(timeAgo("2026-10-24T09:00:00Z", now)).toMatch(/3 hours ago/);
    expect(timeAgo("2026-10-21T12:00:00Z", now)).toMatch(/3 days ago/);
  });
});
