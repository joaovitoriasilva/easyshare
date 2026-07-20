import { computed, ref } from "vue";
import { downloadUrl, streamArchiveDownload } from "@/lib/download";

/**
 * Drives a single archive (zip) download with an in-app progress read-out.
 *
 * The server streams the zip without a `Content-Length`, so progress is measured
 * against the summed sizes of the selected files (`estimatedBytes`). Small
 * archives stream through `fetch` and report progress; archives too large to
 * hold in memory (or any failure) transparently fall back to a plain browser
 * navigation, which shows the browser's own native download progress. The whole
 * thing is cancellable.
 */
export function useArchiveDownload() {
  const downloading = ref(false);
  const received = ref(0);
  const total = ref<number | null>(null);
  const bytesPerSecond = ref(0);
  const etaSeconds = ref<number | null>(null);
  let controller: AbortController | null = null;
  // Sampling cursor for the smoothed transfer-rate estimate.
  let sampleTime = 0;
  let sampleBytes = 0;
  let smoothedBps = 0;

  function resetSpeed(): void {
    bytesPerSecond.value = 0;
    etaSeconds.value = null;
    sampleTime = 0;
    sampleBytes = 0;
    smoothedBps = 0;
  }

  /** Update the smoothed rate and ETA from the latest received/total counters. */
  function sampleSpeed(): void {
    const now =
      typeof performance !== "undefined" ? performance.now() : Date.now();
    if (sampleTime === 0) {
      sampleTime = now;
      sampleBytes = received.value;
      return;
    }
    const dt = (now - sampleTime) / 1000;
    if (dt < 0.4) {
      return;
    }
    const instant = Math.max(0, (received.value - sampleBytes) / dt);
    smoothedBps = smoothedBps === 0 ? instant : smoothedBps * 0.7 + instant * 0.3;
    sampleTime = now;
    sampleBytes = received.value;
    bytesPerSecond.value = smoothedBps;
    const totalBytes = total.value;
    etaSeconds.value =
      totalBytes && totalBytes > 0 && smoothedBps > 0
        ? Math.max(0, (totalBytes - received.value) / smoothedBps)
        : null;
  }

  /** Whole-number percentage, capped at 99 until done, or null when unknown. */
  const percent = computed(() => {
    if (total.value === null || total.value <= 0) {
      return null;
    }
    return Math.min(99, Math.round((received.value / total.value) * 100));
  });

  /** True while streaming with no known total (show an indeterminate bar). */
  const indeterminate = computed(() => downloading.value && percent.value === null);

  async function start(
    url: string,
    filename: string,
    estimatedBytes?: number,
  ): Promise<"completed" | "fell-back" | "canceled"> {
    if (downloading.value) {
      return "canceled";
    }
    downloading.value = true;
    received.value = 0;
    total.value = estimatedBytes && estimatedBytes > 0 ? estimatedBytes : null;
    resetSpeed();
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const outcome = await streamArchiveDownload(url, filename, {
        estimatedBytes,
        signal,
        onProgress: (progress) => {
          received.value = progress.received;
          total.value = progress.total;
          sampleSpeed();
        },
      });
      // Too large for in-memory streaming (or the request failed): let the
      // browser download it natively. A user cancellation must not do this.
      if (outcome === "fell-back") {
        if (signal.aborted) {
          return "canceled";
        }
        downloadUrl(url, filename);
        return "fell-back";
      }
      return "completed";
    } catch {
      if (signal.aborted) {
        return "canceled";
      }
      downloadUrl(url, filename);
      return "fell-back";
    } finally {
      downloading.value = false;
      controller = null;
      resetSpeed();
    }
  }

  function cancel(): void {
    controller?.abort();
  }

  return {
    downloading,
    received,
    total,
    percent,
    indeterminate,
    bytesPerSecond,
    etaSeconds,
    start,
    cancel,
  };
}
