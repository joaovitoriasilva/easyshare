/**
 * Smoothed transfer-rate + ETA estimator shared by file uploads and archive
 * downloads.
 *
 * Feed an instance the cumulative bytes transferred (and the total, when known)
 * as progress events arrive; it debounces samples and applies an exponential
 * moving average so the reported rate is stable rather than jittery. One
 * instance tracks one transfer — uploads keep one per package, archive
 * downloads keep a single one.
 */

// Ignore samples closer together than this so a burst of progress events yields
// a stable rate rather than a noisy one.
const SAMPLE_INTERVAL_MS = 400;
// Exponential-moving-average weight for the newest instantaneous rate.
const SMOOTHING = 0.3;

export interface TransferRate {
  /** Smoothed transfer rate in bytes/second (0 until enough samples exist). */
  bytesPerSecond: number;
  /** Estimated seconds remaining, or null when the total/rate is unknown. */
  etaSeconds: number | null;
}

const IDLE: TransferRate = { bytesPerSecond: 0, etaSeconds: null };

export interface TransferRateTracker {
  /** Feed the latest cumulative counters; returns the current smoothed rate. */
  sample(loaded: number, total: number | null): TransferRate;
  /** Forget all samples (transfer finished or restarted). */
  reset(): void;
  /** The most recently computed rate. */
  readonly current: TransferRate;
}

export function createTransferRate(): TransferRateTracker {
  let sampleTime = 0;
  let sampleBytes = 0;
  let smoothedBps = 0;
  let rate: TransferRate = IDLE;

  return {
    sample(loaded: number, total: number | null): TransferRate {
      const now =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      if (sampleTime === 0) {
        sampleTime = now;
        sampleBytes = loaded;
        return rate;
      }
      const dt = (now - sampleTime) / 1000;
      if (dt < SAMPLE_INTERVAL_MS / 1000) {
        return rate;
      }
      const instant = Math.max(0, (loaded - sampleBytes) / dt);
      smoothedBps =
        smoothedBps === 0
          ? instant
          : smoothedBps * (1 - SMOOTHING) + instant * SMOOTHING;
      sampleTime = now;
      sampleBytes = loaded;
      rate = {
        bytesPerSecond: smoothedBps,
        etaSeconds:
          total && total > 0 && smoothedBps > 0
            ? Math.max(0, (total - loaded) / smoothedBps)
            : null,
      };
      return rate;
    },
    reset(): void {
      sampleTime = 0;
      sampleBytes = 0;
      smoothedBps = 0;
      rate = IDLE;
    },
    get current(): TransferRate {
      return rate;
    },
  };
}
