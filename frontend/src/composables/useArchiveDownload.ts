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
  let controller: AbortController | null = null;

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
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const outcome = await streamArchiveDownload(url, filename, {
        estimatedBytes,
        signal,
        onProgress: (progress) => {
          received.value = progress.received;
          total.value = progress.total;
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
    }
  }

  function cancel(): void {
    controller?.abort();
  }

  return { downloading, received, total, percent, indeterminate, start, cancel };
}
