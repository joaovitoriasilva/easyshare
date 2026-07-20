/** Format a byte count into a human-readable string. */
export function formatBytes(bytes: number): string {
  if (bytes === 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

/** Format a transfer rate (bytes per second) like "1.2 MB/s"; "" when unknown. */
export function formatRate(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) {
    return "";
  }
  return `${formatBytes(bytesPerSecond)}/s`;
}

/**
 * Format a short duration in seconds like "45s", "3m 05s" or "1h 02m".
 *
 * Used for upload/download ETAs. Returns "" for a missing or negative value so
 * callers can hide the read-out until an estimate is available.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return "";
  }
  const total = Math.round(seconds);
  if (total < 60) {
    return `${total}s`;
  }
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes < 60) {
    return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${String(mins).padStart(2, "0")}m`;
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60 * 1000],
  ["month", 30 * 24 * 60 * 60 * 1000],
  ["week", 7 * 24 * 60 * 60 * 1000],
  ["day", 24 * 60 * 60 * 1000],
  ["hour", 60 * 60 * 1000],
  ["minute", 60 * 1000],
  ["second", 1000],
];

/**
 * Format an ISO timestamp relative to now, e.g. "in 3 days" or "2 hours ago".
 *
 * Uses `Intl.RelativeTimeFormat` so the phrasing is localised. Returns an empty
 * string for a missing/unparseable value so callers can fall back cleanly.
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) {
    return "";
  }
  const diff = target - Date.now();
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, ms] of RELATIVE_UNITS) {
    if (Math.abs(diff) >= ms || unit === "second") {
      return formatter.format(Math.round(diff / ms), unit);
    }
  }
  return "";
}
