/**
 * Clicks a hidden anchor to trigger a browser download for an existing URL
 * (e.g. an authorized API endpoint). Adds `rel="noopener"` and appends the
 * anchor to the DOM so the click is honored across browsers (notably Firefox).
 */
export function downloadUrl(url: string, filename: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * Triggers a browser download for an in-memory Blob, revoking the temporary
 * object URL afterwards so the blob can be garbage-collected.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    downloadUrl(url, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Progress of a streamed archive download; `total` is null when unknown. */
export interface ArchiveProgress {
  received: number;
  total: number | null;
}

/** Whether the streamed download finished in-app or must fall back to a plain navigation. */
export type StreamOutcome = "completed" | "fell-back";

interface StreamOptions {
  /** Best-effort expected size (sum of the selected files) for a % readout. */
  estimatedBytes?: number;
  signal?: AbortSignal;
  onProgress?: (progress: ArchiveProgress) => void;
}

// Archives up to this size are streamed and assembled in memory so the app can
// show real progress; anything larger is left to the browser's native download
// (which has its own progress UI) rather than risk exhausting a tab's memory.
const IN_MEMORY_LIMIT = 500 * 1024 * 1024;

/**
 * Stream a zip archive with progress, assembling it in memory and saving it via
 * a Blob. Returns `"fell-back"` (without downloading) when the archive is too
 * large to hold in memory, the request fails, or the body can't be streamed, so
 * the caller can trigger a plain navigation instead. The server streams the zip
 * without a `Content-Length`, so progress is measured against `estimatedBytes`
 * (the summed file sizes); it stays indeterminate when that is unknown.
 */
export async function streamArchiveDownload(
  url: string,
  filename: string,
  options: StreamOptions = {},
): Promise<StreamOutcome> {
  const estimated =
    options.estimatedBytes && options.estimatedBytes > 0
      ? options.estimatedBytes
      : null;
  // Refuse up front to buffer an archive that could exhaust memory.
  if (estimated !== null && estimated > IN_MEMORY_LIMIT) {
    return "fell-back";
  }

  let response: Response;
  try {
    response = await fetch(url, { signal: options.signal });
  } catch (error) {
    if (options.signal?.aborted) {
      throw error;
    }
    return "fell-back";
  }
  if (!response.ok || !response.body) {
    return "fell-back";
  }

  const headerLength = Number(response.headers.get("content-length"));
  const total =
    Number.isFinite(headerLength) && headerLength > 0 ? headerLength : estimated;

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    received += value.byteLength;
    // A missing/under-estimated size could still blow past the guard mid-stream.
    if (received > IN_MEMORY_LIMIT) {
      await reader.cancel();
      return "fell-back";
    }
    chunks.push(value);
    options.onProgress?.({ received, total });
  }
  downloadBlob(new Blob(chunks as BlobPart[], { type: "application/zip" }), filename);
  return "completed";
}
