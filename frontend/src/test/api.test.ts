import { describe, expect, it, vi, afterEach } from "vitest";
import { adminApi, auditApi, packagesApi, publicApi } from "@/api";
import { ApiError, getToken, setToken, setUnauthorizedHandler } from "@/api/client";

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

describe("packagesApi.list", () => {
  const jsonResponse = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  it("requests a single page with limit and offset", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ items: [{ id: 1 }], total: 30, limit: 12, offset: 12 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const page = await packagesApi.list({ limit: 12, offset: 12 });

    expect(page.total).toBe(30);
    expect(page.items).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/packages?");
    expect(url).toContain("limit=12");
    expect(url).toContain("offset=12");
  });

  it("defaults limit and offset when omitted", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await packagesApi.list();

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("limit=50");
    expect(url).toContain("offset=0");
  });
});

describe("auditApi", () => {
  const jsonResponse = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  it("requests owner-scoped activity with pagination and filters", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await auditApi.mine({ action: "share.download", offset: 100 });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/audit/mine?");
    expect(url).toContain("action=share.download");
    expect(url).toContain("offset=100");
    expect(url).toContain("limit=50");
  });

  it("requests the admin-wide log at /audit", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await auditApi.all({ actor: "user:1" });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/audit?");
    expect(url).toContain("actor=user%3A1");
  });
});

describe("adminApi", () => {
  const jsonResponse = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  it("lists users with pagination", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await adminApi.listUsers({ offset: 50 });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/admin/users?");
    expect(url).toContain("offset=50");
  });

  it("patches a user with PATCH", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 3, is_admin: true }));
    vi.stubGlobal("fetch", fetchMock);

    await adminApi.updateUser(3, { is_admin: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/admin/users/3");
    expect((init as RequestInit).method).toBe("PATCH");
  });

  it("sets all quotas with PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ updated: 3 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await adminApi.setAllQuotas(1048576);

    expect(result).toEqual({ updated: 3 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/admin/users/quota");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ storage_quota: 1048576 });
  });
});

describe("packagesApi.update", () => {
  const jsonResponse = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  it("sends a PATCH with the changed name and description", async () => {
    const updated = { id: 7, name: "New name", description: "New desc", files: [] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(updated));
    vi.stubGlobal("fetch", fetchMock);

    const result = await packagesApi.update(7, {
      name: "New name",
      description: "New desc",
    });

    expect(result).toMatchObject({ id: 7, name: "New name" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/packages/7");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({
      name: "New name",
      description: "New desc",
    });
  });
});

describe("packagesApi stats and bulk file actions", () => {
  const jsonResponse = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  it("fetches package stats", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ views: 3, downloads: 5, file_downloads: { 1: 5 } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await packagesApi.stats(7);

    expect(result).toEqual({ views: 3, downloads: 5, file_downloads: { 1: 5 } });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/packages/7/stats");
  });

  it("builds the download-all url with a token", () => {
    expect(packagesApi.downloadAllUrl(7, "tok.jwt")).toBe(
      "/api/packages/7/download?token=tok.jwt",
    );
  });

  it("builds a file download url with a token", () => {
    expect(packagesApi.fileDownloadUrl(7, 3, "tok.jwt")).toBe(
      "/api/packages/7/files/3/download?token=tok.jwt",
    );
  });

  it("requests a download token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ token: "abc" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await packagesApi.downloadToken(7);

    expect(result).toEqual({ token: "abc" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/packages/7/download-token");
    expect(init.method).toBe("POST");
  });

  it("sends a DELETE to remove all files", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "All files deleted" }));
    vi.stubGlobal("fetch", fetchMock);

    await packagesApi.removeAllFiles(7);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/packages/7/files");
    expect(init.method).toBe("DELETE");
  });
});


describe("packagesApi.uploadFile", () => {
  type ProgressLike = { lengthComputable: boolean; loaded: number; total: number };

  class FakeUpload {
    handler: ((event: ProgressLike) => void) | null = null;
    addEventListener(type: string, cb: (event: ProgressLike) => void): void {
      if (type === "progress") {
        this.handler = cb;
      }
    }
  }

  class FakeXhr {
    status = 0;
    statusText = "";
    responseText = "";
    upload = new FakeUpload();
    private onLoad: (() => void) | null = null;
    open(): void {}
    setRequestHeader(): void {}
    addEventListener(type: string, cb: () => void): void {
      if (type === "load") {
        this.onLoad = cb;
      }
    }
    send(): void {
      this.upload.handler?.({ lengthComputable: true, loaded: 5, total: 10 });
      this.upload.handler?.({ lengthComputable: true, loaded: 10, total: 10 });
      this.status = 201;
      this.responseText = JSON.stringify({ id: 1 });
      this.onLoad?.();
    }
  }

  it("uploads via XHR and reports progress", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const fractions: number[] = [];

    await packagesApi.uploadFile(7, new File(["data"], "a.txt"), (fraction) =>
      fractions.push(fraction),
    );

    expect(fractions).toEqual([0.5, 1]);
    vi.unstubAllGlobals();
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

describe("unauthorized handling", () => {
  const unauthorized = (): Response =>
    new Response(JSON.stringify({ detail: "Not authenticated" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });

  it("invokes the handler on a 401 for authenticated requests", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setToken("expired");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(unauthorized()));

    await expect(packagesApi.get(1)).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();

    setUnauthorizedHandler(null);
  });

  it("ignores 401s from unauthenticated (auth:false) requests", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(unauthorized()));

    await expect(publicApi.view("x")).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();

    setUnauthorizedHandler(null);
  });
});
