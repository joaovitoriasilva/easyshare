/**
 * Resolves a post-login redirect target while blocking open redirects. Only
 * internal absolute paths (a single leading slash, no scheme or host) are
 * allowed; anything else — external URLs (`//evil.com`, `https://…`) or
 * script pseudo-schemes (`javascript:`) — falls back to `fallback`.
 */
export function getSafeRedirect(value: unknown, fallback = "/dashboard"): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (
    typeof candidate === "string" &&
    candidate.startsWith("/") &&
    !candidate.startsWith("//") &&
    !candidate.includes("://")
  ) {
    return candidate;
  }
  return fallback;
}
