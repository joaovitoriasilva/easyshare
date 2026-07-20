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
