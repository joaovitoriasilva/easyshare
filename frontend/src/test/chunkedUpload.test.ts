import { beforeEach, describe, expect, it } from "vitest";
import { listResumableUploads } from "@/lib/chunkedUpload";

describe("listResumableUploads", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns only entries for the given package, parsed from JSON", () => {
    localStorage.setItem(
      "easyshare_upload:7:report.pdf:1024:1699999999000",
      JSON.stringify({
        uploadId: "abc",
        filename: "report.pdf",
        size: 1024,
        lastModified: 1699999999000,
      }),
    );
    localStorage.setItem(
      "easyshare_upload:8:other.zip:2048:1700000000000",
      JSON.stringify({
        uploadId: "def",
        filename: "other.zip",
        size: 2048,
        lastModified: 1700000000000,
      }),
    );
    localStorage.setItem("unrelated-key", "ignored");

    const found = listResumableUploads(7);

    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({
      key: "easyshare_upload:7:report.pdf:1024:1699999999000",
      packageId: 7,
      uploadId: "abc",
      filename: "report.pdf",
      size: 1024,
      lastModified: 1699999999000,
    });
  });

  it("prunes and skips a corrupt entry", () => {
    const key = "easyshare_upload:7:bad.txt:1:2";
    localStorage.setItem(key, "not json");

    expect(listResumableUploads(7)).toEqual([]);
    expect(localStorage.getItem(key)).toBeNull();
  });
});
