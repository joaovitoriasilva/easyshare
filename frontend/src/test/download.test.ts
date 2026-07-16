import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadBlob, downloadUrl } from "@/lib/download";

describe("download helpers", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("downloadBlob creates and then revokes the object URL (no leak)", () => {
    downloadBlob(new Blob(["hello"]), "file.txt");
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
  });

  it("downloadUrl triggers a download without touching object URLs", () => {
    downloadUrl("/api/file", "file.txt");
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });
});
