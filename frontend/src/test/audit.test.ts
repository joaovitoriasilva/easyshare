import { describe, expect, it } from "vitest";
import {
  formatAuditAction,
  formatAuditActor,
  formatAuditDetail,
  formatAuditTarget,
} from "@/lib/audit";

describe("audit formatting", () => {
  it("uses readable labels for known and future actions", () => {
    expect(formatAuditAction("share.enable")).toBe("Sharing enabled");
    expect(formatAuditAction("file.upload_complete")).toBe("File upload complete");
  });

  it("formats internal references without exposing raw prefixes", () => {
    expect(formatAuditActor("user:12")).toBe("User #12");
    expect(formatAuditActor(null)).toBe("Anonymous");
    expect(formatAuditTarget("package:7")).toBe("Package #7");
    expect(formatAuditTarget("share:abc123")).toBe("Share abc123");
  });

  it("formats event details as readable metadata", () => {
    expect(
      formatAuditDetail({ filename: "brief.pdf", archive: true, file_ids: [2, 3] }),
    ).toBe("Filename: brief.pdf · Archive: Yes · Files: 2, 3");
    expect(formatAuditDetail(null)).toBe("");
  });
});