/**
 * Copy text to the clipboard with a graceful fallback.
 *
 * Uses the async Clipboard API when available (secure contexts), and falls back
 * to a hidden `<textarea>` + `document.execCommand("copy")` when it is missing
 * or rejects — for example on plain-HTTP origins or older browsers where
 * `navigator.clipboard` is undefined. Resolves `true` when the copy succeeded.
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through to the legacy path below */
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  // Keep it off-screen so it doesn't disrupt scroll position or layout.
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";
  document.body.append(textarea);

  const selection = document.getSelection();
  const previousRange =
    selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  textarea.remove();

  // Restore any selection the user had before we hijacked it.
  if (previousRange && selection) {
    selection.removeAllRanges();
    selection.addRange(previousRange);
  }
  return copied;
}

/** Outcome of {@link shareOrCopy}: the native share sheet, a clipboard copy, or nothing. */
export type ShareResult = "shared" | "copied" | "failed";

/**
 * Offer the native share sheet (mobile/`navigator.share`) and fall back to
 * copying the URL to the clipboard.
 *
 * Returns `"shared"` when the OS share sheet completed, `"copied"` when the URL
 * was placed on the clipboard instead, and `"failed"` if neither worked. A user
 * dismissing the share sheet (`AbortError`) is treated as handled, not a
 * failure, so the caller does not then also copy behind their back.
 */
export async function shareOrCopy(data: {
  url: string;
  title?: string;
  text?: string;
}): Promise<ShareResult> {
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title: data.title, text: data.text, url: data.url });
      return "shared";
    } catch (error) {
      // The user cancelled the share sheet: nothing more to do.
      if (error instanceof DOMException && error.name === "AbortError") {
        return "shared";
      }
      // Any other failure falls through to the clipboard path below.
    }
  }
  return (await copyText(data.url)) ? "copied" : "failed";
}

