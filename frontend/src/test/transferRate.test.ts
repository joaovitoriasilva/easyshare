import { afterEach, describe, expect, it, vi } from "vitest";
import { createTransferRate } from "@/lib/transferRate";

describe("createTransferRate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stays idle until a second sample past the debounce interval", () => {
    const now = vi.spyOn(performance, "now");
    now.mockReturnValue(1000);
    const tracker = createTransferRate();
    // First sample only establishes the baseline.
    expect(tracker.sample(0, 1000)).toEqual({ bytesPerSecond: 0, etaSeconds: null });
    // Within the 400ms window: no rate yet.
    now.mockReturnValue(1100);
    expect(tracker.sample(50, 1000)).toEqual({ bytesPerSecond: 0, etaSeconds: null });
    // One second after the baseline, 500 bytes transferred → 500 B/s, 1s ETA.
    now.mockReturnValue(2000);
    const rate = tracker.sample(500, 1000);
    expect(rate.bytesPerSecond).toBeCloseTo(500);
    expect(rate.etaSeconds).toBeCloseTo(1);
    expect(tracker.current).toEqual(rate);
  });

  it("reports no ETA when the total is unknown", () => {
    const now = vi.spyOn(performance, "now");
    now.mockReturnValue(1000);
    const tracker = createTransferRate();
    tracker.sample(0, null);
    now.mockReturnValue(2000);
    const rate = tracker.sample(500, null);
    expect(rate.bytesPerSecond).toBeGreaterThan(0);
    expect(rate.etaSeconds).toBeNull();
  });

  it("reset() forgets accumulated samples", () => {
    const now = vi.spyOn(performance, "now");
    now.mockReturnValue(1000);
    const tracker = createTransferRate();
    tracker.sample(0, 1000);
    now.mockReturnValue(2000);
    tracker.sample(500, 1000);
    tracker.reset();
    expect(tracker.current).toEqual({ bytesPerSecond: 0, etaSeconds: null });
    // The first sample after a reset re-establishes a baseline (idle again).
    now.mockReturnValue(2100);
    expect(tracker.sample(600, 1000)).toEqual({ bytesPerSecond: 0, etaSeconds: null });
  });
});
