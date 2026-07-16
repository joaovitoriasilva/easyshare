import { describe, expect, it, vi, afterEach } from "vitest";
import { publicApi } from "@/api";
import { ApiError, getToken, setToken } from "@/api/client";

afterEach(() => {
  vi.restoreAllMocks();
  setToken(null);
});

describe("token storage", () => {
  it("stores and clears the auth token", () => {
    expect(getToken()).toBeNull();
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});

describe("publicApi url builders", () => {
  it("builds a download url with selected file ids", () => {
    const url = publicApi.downloadUrl("tok", [1, 2], null);
    expect(url).toBe("/api/s/tok/download?file_ids=1&file_ids=2");
  });

  it("omits the query when no files or token are given", () => {
    expect(publicApi.downloadUrl("tok", [], null)).toBe("/api/s/tok/download");
  });

  it("includes the access token for restricted downloads", () => {
    const url = publicApi.fileUrl("tok", 5, "signed.jwt.token");
    expect(url).toContain("access=signed.jwt.token");
    expect(url).not.toContain("email");
    expect(url).toContain("/api/s/tok/files/5/download");
  });
});

describe("api error handling", () => {
  it("throws ApiError with the server detail message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Share not found" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    await expect(publicApi.view("missing")).rejects.toMatchObject({
      status: 404,
      message: "Share not found",
    } satisfies Partial<ApiError>);
  });
});
