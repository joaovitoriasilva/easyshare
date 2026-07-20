import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText, shareOrCopy } from "@/lib/clipboard";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("copyText", () => {
  it("uses the async clipboard API when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    const ok = await copyText("hello");

    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to execCommand when the clipboard API is missing", async () => {
    vi.stubGlobal("navigator", {});
    const execCommand = vi.fn().mockReturnValue(true);
    // jsdom does not implement execCommand; provide it.
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });

    const ok = await copyText("world");

    expect(ok).toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });

  it("falls back when the async clipboard API rejects", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });

    const ok = await copyText("again");

    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalled();
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});

describe("shareOrCopy", () => {
  it("uses the native share sheet when available", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { share });

    const result = await shareOrCopy({ url: "https://x/y", title: "T" });

    expect(result).toBe("shared");
    expect(share).toHaveBeenCalledWith({ title: "T", text: undefined, url: "https://x/y" });
  });

  it("treats a cancelled share sheet as handled", async () => {
    const share = vi
      .fn()
      .mockRejectedValue(new DOMException("cancelled", "AbortError"));
    vi.stubGlobal("navigator", { share });

    expect(await shareOrCopy({ url: "https://x/y" })).toBe("shared");
  });

  it("copies the URL when the share API is missing", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    const result = await shareOrCopy({ url: "https://x/y" });

    expect(result).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("https://x/y");
  });
});
