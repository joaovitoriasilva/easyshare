import { describe, expect, it } from "vitest";
import { estimatePasswordStrength } from "@/lib/passwordStrength";

describe("estimatePasswordStrength", () => {
  it("scores an empty password as 0 with no label", () => {
    expect(estimatePasswordStrength("")).toEqual({ score: 0, label: "" });
  });

  it("caps a below-minimum password at Weak however varied", () => {
    // 5 chars but all four character classes present.
    expect(estimatePasswordStrength("aB3$x")).toEqual({ score: 1, label: "Weak" });
  });

  it("rates a plain 8-char password Weak", () => {
    expect(estimatePasswordStrength("abcdefgh")).toEqual({ score: 1, label: "Weak" });
  });

  it("rates length or variety as Fair", () => {
    expect(estimatePasswordStrength("abcdefgh1").label).toBe("Fair");
    expect(estimatePasswordStrength("abcdefghijkl").label).toBe("Fair");
  });

  it("rates a mixed 10-char password Good", () => {
    expect(estimatePasswordStrength("Abcdefgh1!")).toEqual({ score: 3, label: "Good" });
  });

  it("rates a long, varied password Strong", () => {
    expect(estimatePasswordStrength("Abcdefghijkl1!")).toEqual({
      score: 4,
      label: "Strong",
    });
  });
});
