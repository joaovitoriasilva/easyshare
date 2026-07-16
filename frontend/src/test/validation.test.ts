import { describe, expect, it } from "vitest";
import { invalidEmails, isValidEmail, parseEmailList } from "@/lib/validation";

describe("isValidEmail", () => {
  it("accepts well-formed addresses (trimming whitespace)", () => {
    expect(isValidEmail("alice@example.com")).toBe(true);
    expect(isValidEmail("  a.b-c@sub.example.co  ")).toBe(true);
  });

  it("rejects malformed addresses", () => {
    for (const bad of ["", "alice", "alice@", "@example.com", "a@b", "a b@c.com"]) {
      expect(isValidEmail(bad)).toBe(false);
    }
  });
});

describe("email list helpers", () => {
  it("parses comma/whitespace separated lists", () => {
    expect(parseEmailList("a@b.com, c@d.com  e@f.com")).toEqual([
      "a@b.com",
      "c@d.com",
      "e@f.com",
    ]);
  });

  it("returns only the malformed entries", () => {
    expect(invalidEmails("a@b.com, nope, c@d.org")).toEqual(["nope"]);
    expect(invalidEmails("a@b.com")).toEqual([]);
  });
});
