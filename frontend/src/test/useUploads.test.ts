import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";

const { uploadFileMock } = vi.hoisted(() => ({ uploadFileMock: vi.fn() }));

vi.mock("@/api", () => ({
  packagesApi: { uploadFile: uploadFileMock },
}));

// Keep the composable isolated from real toasts (and their timers).
vi.mock("@/composables/useToasts", () => ({
  useToasts: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    notify: vi.fn(),
    dismiss: vi.fn(),
    toasts: { value: [] },
  }),
}));

// The composable reads chunk-upload settings from the auth store; stub it so the
// test needs no Pinia and small files take the single-request path.
vi.mock("@/stores/auth", () => ({
  useAuthStore: () => ({ chunkUploadsEnabled: true, chunkSize: 8 * 1024 * 1024 }),
}));

import { useUploads } from "@/composables/useUploads";

const makeFile = (name: string, bytes = "ab"): File => new File([bytes], name);

beforeEach(() => {
  uploadFileMock.mockReset();
});

describe("useUploads", () => {
  it("uploads files and clears the batch once all succeed", async () => {
    uploadFileMock.mockImplementation(
      (_id: number, _file: File, onProgress?: (f: number) => void) => {
        onProgress?.(0.5);
        onProgress?.(1);
        return Promise.resolve();
      },
    );
    const { uploadsFor, isUploading, startUploads } = useUploads();
    const items = uploadsFor(1);

    const count = await startUploads(1, [makeFile("a.txt")], 1000);

    expect(count).toBe(1);
    expect(isUploading(1).value).toBe(false);
    expect(items.value).toEqual([]);
  });

  it("runs at most UPLOAD_CONCURRENCY uploads at once", async () => {
    let inFlight = 0;
    let peak = 0;
    const pending: Array<() => void> = [];
    uploadFileMock.mockImplementation(() => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      return new Promise<void>((resolve) => {
        pending.push(() => {
          inFlight -= 1;
          resolve();
        });
      });
    });

    const { startUploads, uploadsFor } = useUploads();
    const files = ["a", "b", "c", "d", "e"].map((n) => makeFile(n));
    const done = startUploads(20, files, 1000);

    // The pool saturates synchronously; only three uploads run concurrently.
    await Promise.resolve();
    expect(peak).toBe(3);
    expect(inFlight).toBe(3);

    // Resolve uploads one at a time; each completion frees a slot for the next.
    let guard = 0;
    while (pending.length > 0 && guard < 100) {
      pending.shift()?.();
      await Promise.resolve();
      await Promise.resolve();
      guard += 1;
    }
    await done;

    expect(peak).toBe(3);
    expect(uploadFileMock).toHaveBeenCalledTimes(5);
    expect(uploadsFor(20).value).toEqual([]);
  });

  it("exposes in-flight progress to any caller, surviving a remount", async () => {
    let resolveUpload: () => void = () => {};
    let report: ((fraction: number) => void) | undefined;
    uploadFileMock.mockImplementation(
      (_id: number, _file: File, onProgress?: (f: number) => void) => {
        report = onProgress;
        return new Promise<void>((resolve) => {
          resolveUpload = resolve;
        });
      },
    );

    // The view that started the upload.
    const started = useUploads();
    const done = started.startUploads(2, [makeFile("a.txt")], 1000);

    // A fresh composable instance (like the view remounted after navigating
    // away and back) sees the same in-flight batch and its progress.
    const remounted = useUploads();
    const items = remounted.uploadsFor(2);
    expect(remounted.isUploading(2).value).toBe(true);
    expect(items.value).toHaveLength(1);
    expect(items.value[0].progress).toBe(0);

    report?.(0.42);
    expect(items.value[0].progress).toBe(0.42);

    resolveUpload();
    await done;
    expect(remounted.isUploading(2).value).toBe(false);
  });

  it("rejects files over the size limit and uploads the rest", async () => {
    uploadFileMock.mockResolvedValue(undefined);
    const { startUploads, isUploading } = useUploads();
    const big = makeFile("big.txt", "abcdef"); // 6 bytes
    const small = makeFile("small.txt", "ab"); // 2 bytes

    const count = await startUploads(3, [big, small], 3);

    expect(count).toBe(1);
    expect(uploadFileMock).toHaveBeenCalledTimes(1);
    expect(uploadFileMock.mock.calls[0][1]).toBe(small);
    expect(isUploading(3).value).toBe(false);
  });

  it("keeps a failed batch visible instead of clearing it", async () => {
    uploadFileMock.mockRejectedValue(new ApiError(500, "boom"));
    const { startUploads, uploadsFor, isUploading } = useUploads();

    const count = await startUploads(4, [makeFile("a.txt")], 1000);

    expect(count).toBe(0);
    expect(isUploading(4).value).toBe(false);
    const items = uploadsFor(4).value;
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("error");
  });

  it("cancels an in-flight upload, keeping it visible as canceled", async () => {
    uploadFileMock.mockImplementation(
      (
        _id: number,
        _file: File,
        _onProgress?: (f: number) => void,
        signal?: AbortSignal,
      ) =>
        new Promise<void>((_resolve, reject) => {
          signal?.addEventListener("abort", () =>
            reject(new ApiError(0, "Upload canceled")),
          );
        }),
    );
    const { startUploads, cancelUpload, uploadsFor, isUploading } = useUploads();
    const done = startUploads(10, [makeFile("a.txt")], 1000);
    const items = uploadsFor(10);
    expect(items.value[0].status).toBe("uploading");

    cancelUpload(10, 0);
    await done;

    expect(isUploading(10).value).toBe(false);
    expect(items.value).toHaveLength(1);
    expect(items.value[0].status).toBe("canceled");
  });

  it("retries a failed upload and clears the batch on success", async () => {
    uploadFileMock.mockRejectedValueOnce(new ApiError(500, "boom"));
    uploadFileMock.mockResolvedValueOnce(undefined);
    const { startUploads, retryUpload, uploadsFor, isUploading } = useUploads();

    await startUploads(11, [makeFile("a.txt")], 1000);
    expect(uploadsFor(11).value[0].status).toBe("error");

    const ok = await retryUpload(11, 0);

    expect(ok).toBe(true);
    expect(isUploading(11).value).toBe(false);
    expect(uploadsFor(11).value).toEqual([]);
  });

  it("retries every failed file at once and clears the batch on success", async () => {
    uploadFileMock
      .mockRejectedValueOnce(new ApiError(500, "boom"))
      .mockRejectedValueOnce(new ApiError(500, "boom"))
      .mockResolvedValue(undefined);
    const { startUploads, retryAllFailed, uploadsFor, isUploading } = useUploads();

    await startUploads(13, [makeFile("a.txt"), makeFile("b.txt")], 1000);
    const items = uploadsFor(13);
    expect(items.value).toHaveLength(2);
    expect(items.value.every((item) => item.status === "error")).toBe(true);

    const retried = await retryAllFailed(13);

    expect(retried).toBe(2);
    expect(isUploading(13).value).toBe(false);
    expect(items.value).toEqual([]);
  });

  it("retryAllFailed is a no-op when nothing failed", async () => {
    uploadFileMock.mockResolvedValue(undefined);
    const { startUploads, retryAllFailed } = useUploads();

    await startUploads(14, [makeFile("a.txt")], 1000);
    expect(await retryAllFailed(14)).toBe(0);
  });

  it("dismisses a failed upload row", async () => {
    uploadFileMock.mockRejectedValue(new ApiError(500, "boom"));
    const { startUploads, dismissUpload, uploadsFor } = useUploads();

    await startUploads(12, [makeFile("a.txt")], 1000);
    expect(uploadsFor(12).value).toHaveLength(1);

    dismissUpload(12, 0);
    expect(uploadsFor(12).value).toEqual([]);
  });

  it("clears completed rows but keeps failed ones", async () => {
    uploadFileMock
      .mockResolvedValueOnce(undefined) // a.txt succeeds
      .mockRejectedValueOnce(new ApiError(500, "boom")); // b.txt fails
    const { startUploads, clearCompleted, uploadsFor } = useUploads();

    await startUploads(300, [makeFile("a.txt"), makeFile("b.txt")], 1000);
    const items = uploadsFor(300);
    expect(items.value).toHaveLength(2);
    expect([...items.value].map((item) => item.status).sort()).toEqual([
      "done",
      "error",
    ]);

    clearCompleted(300);

    expect(items.value).toHaveLength(1);
    expect(items.value[0].status).toBe("error");
  });
});
