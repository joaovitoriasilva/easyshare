import { describe, expect, it } from "vitest";
import {
  formatBytes,
  formatDuration,
  formatRate,
  formatRelativeTime,
} from "@/lib/format";
import { cn } from "@/lib/utils";

describe("formatBytes", () => {
  it("formats zero bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("formatRate", () => {
  it("returns an empty string for a non-positive or invalid rate", () => {
    expect(formatRate(0)).toBe("");
    expect(formatRate(-1)).toBe("");
    expect(formatRate(Number.NaN)).toBe("");
  });

  it("formats a positive rate with a /s suffix", () => {
    expect(formatRate(2048)).toBe("2.0 KB/s");
    expect(formatRate(5 * 1024 * 1024)).toBe("5.0 MB/s");
  });
});

describe("formatDuration", () => {
  it("returns an empty string for a missing or negative value", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(undefined)).toBe("");
    expect(formatDuration(-5)).toBe("");
    expect(formatDuration(Number.NaN)).toBe("");
  });

  it("formats seconds", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(45)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(185)).toBe("3m 05s");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(3720)).toBe("1h 02m");
  });
});

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("px-2", "py-2")).toContain("px-2");
  });

  it("resolves tailwind conflicts, keeping the last", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("ignores falsy values", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });
});

describe("formatRelativeTime", () => {
  it("returns an empty string for missing or invalid values", () => {
    expect(formatRelativeTime(null)).toBe("");
    expect(formatRelativeTime(undefined)).toBe("");
    expect(formatRelativeTime("not-a-date")).toBe("");
  });

  it("phrases a future time as 'in ...'", () => {
    const future = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(future)).toContain("in 3 day");
  });

  it("phrases a past time as '... ago'", () => {
    const past = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(past)).toContain("hour");
    expect(formatRelativeTime(past)).toContain("ago");
  });
});
