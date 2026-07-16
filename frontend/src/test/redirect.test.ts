import { describe, expect, it } from "vitest";
import { getSafeRedirect } from "@/lib/redirect";

describe("getSafeRedirect", () => {
  it("allows internal absolute paths", () => {
    expect(getSafeRedirect("/dashboard")).toBe("/dashboard");
    expect(getSafeRedirect("/packages/42")).toBe("/packages/42");
  });

  it("takes the first value from an array query", () => {
    expect(getSafeRedirect(["/activity", "/other"])).toBe("/activity");
  });

  it("rejects protocol-relative and absolute URLs", () => {
    expect(getSafeRedirect("//evil.com")).toBe("/dashboard");
    expect(getSafeRedirect("https://evil.com")).toBe("/dashboard");
  });

  it("rejects script pseudo-schemes and non-path values", () => {
    expect(getSafeRedirect("javascript:alert(1)")).toBe("/dashboard");
    expect(getSafeRedirect("dashboard")).toBe("/dashboard");
    expect(getSafeRedirect(null)).toBe("/dashboard");
    expect(getSafeRedirect(undefined)).toBe("/dashboard");
  });

  it("honors a custom fallback", () => {
    expect(getSafeRedirect(null, "/login")).toBe("/login");
  });
});
