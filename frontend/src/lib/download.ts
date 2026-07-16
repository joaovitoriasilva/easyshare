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
