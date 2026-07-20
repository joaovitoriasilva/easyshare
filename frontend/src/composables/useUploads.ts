import { computed, reactive, type ComputedRef } from "vue";
import { packagesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PackageFile } from "@/api/types";
import { uploadFileChunked } from "@/lib/chunkedUpload";
import { useAuthStore } from "@/stores/auth";
import { useToasts } from "@/composables/useToasts";
import { formatBytes } from "@/lib/format";

/** A single file's progress within an in-flight upload batch. */
export interface UploadItem {
  id: number;
  name: string;
  progress: number;
  status: "uploading" | "done" | "error" | "canceled";
}

interface PackageUpload {
  items: UploadItem[];
  active: boolean;
  /** Package display name, for the global indicator. */
  name: string;
}

/** Aggregated view of one package's in-flight batch, for the global indicator. */
export interface UploadBatchSummary {
  packageId: number;
  name: string;
  total: number;
  done: number;
  uploading: number;
  failed: number;
  percent: number;
}

/**
 * Non-reactive side-state for controlling a batch: the source files (needed to
 * retry) and one `AbortController` per file (needed to cancel). Kept out of the
 * reactive store so wrapping an `AbortController` in a Vue proxy can't break its
 * native methods, and so holding a `File` reference never triggers renders.
 */
interface UploadControl {
  files: File[];
  controllers: (AbortController | null)[];
  /** Indices cancelled while still queued, so the loop skips them when reached. */
  canceled: Set<number>;
  /** Called with each successfully-created file so a view can append it in place. */
  onUploaded?: (file: PackageFile) => void;
}

/**
 * In-flight uploads keyed by package id. Module-level (like `useToasts`) so an
 * upload's progress survives navigating away from a package and back: the view
 * is unmounted and remounted, but the state and the running upload loop live
 * here rather than inside the component.
 */
const uploadsByPackage = reactive(new Map<number, PackageUpload>());
const controlByPackage = new Map<number, UploadControl>();

// Aggregated summaries of every currently-active batch, shared by the global
// upload indicator. Reading the reactive Map inside the computed tracks both
// membership changes and the per-item progress/status mutated through the
// stored reactive entries.
const activeBatches = computed<UploadBatchSummary[]>(() => {
  const summaries: UploadBatchSummary[] = [];
  for (const [packageId, batch] of uploadsByPackage) {
    if (!batch.active) {
      continue;
    }
    const total = batch.items.length;
    let progressSum = 0;
    let done = 0;
    let uploading = 0;
    let failed = 0;
    for (const item of batch.items) {
      progressSum += item.progress;
      if (item.status === "done") {
        done += 1;
      } else if (item.status === "uploading") {
        uploading += 1;
      } else {
        failed += 1;
      }
    }
    summaries.push({
      packageId,
      name: batch.name || `Package #${packageId}`,
      total,
      done,
      uploading,
      failed,
      percent: total > 0 ? Math.round((progressSum / total) * 100) : 0,
    });
  }
  return summaries;
});

const hasActiveUploads = computed(() => activeBatches.value.length > 0);

const EMPTY: UploadItem[] = [];
let nextItemId = 0;

// How many files upload at once within a batch. A small pool speeds up
// multi-file uploads while keeping per-file progress readable and staying under
// the browser's per-host connection limit.
const UPLOAD_CONCURRENCY = 3;

export function useUploads() {
  const toast = useToasts();
  const auth = useAuthStore();

  /** Reactive list of the current upload batch for a package (empty if none). */
  function uploadsFor(packageId: number): ComputedRef<UploadItem[]> {
    return computed(() => uploadsByPackage.get(packageId)?.items ?? EMPTY);
  }

  /** Whether a package currently has an upload batch in progress. */
  function isUploading(packageId: number): ComputedRef<boolean> {
    return computed(() => uploadsByPackage.get(packageId)?.active ?? false);
  }

  /**
   * Point the "file uploaded" callback of an in-progress batch at `callback`.
   *
   * A batch outlives the component that started it, so a view that unmounts and
   * remounts mid-upload calls this to re-attach its own optimistic-append
   * handler; a no-op when no batch is running for the package.
   */
  function bindUploaded(
    packageId: number,
    callback: (file: PackageFile) => void,
  ): void {
    const control = controlByPackage.get(packageId);
    if (control) {
      control.onUploaded = callback;
    }
  }

  /** Drop the batch once it is idle and every file finished successfully. */
  function cleanup(packageId: number): void {
    const entry = uploadsByPackage.get(packageId);
    if (entry && !entry.active && entry.items.every((item) => item.status === "done")) {
      uploadsByPackage.delete(packageId);
      controlByPackage.delete(packageId);
    }
  }

  /** Upload the file at `index`, updating its item's progress/status in place. */
  async function uploadOne(packageId: number, index: number): Promise<boolean> {
    const entry = uploadsByPackage.get(packageId);
    const control = controlByPackage.get(packageId);
    if (!entry || !control) {
      return false;
    }
    const item = entry.items[index];
    if (control.canceled.has(index)) {
      item.status = "canceled";
      return false;
    }
    const controller = new AbortController();
    control.controllers[index] = controller;
    item.status = "uploading";
    item.progress = 0;
    try {
      const file = control.files[index];
      // Large files use the resumable, chunked flow so a dropped connection
      // resumes instead of restarting; small ones use the single-request upload.
      const useChunked =
        auth.chunkUploadsEnabled && file.size > auth.chunkSize;
      const created = useChunked
        ? await uploadFileChunked(packageId, file, {
            chunkSize: auth.chunkSize,
            onProgress: (fraction) => {
              item.progress = fraction;
            },
            signal: controller.signal,
          })
        : await packagesApi.uploadFile(
            packageId,
            file,
            (fraction) => {
              item.progress = fraction;
            },
            controller.signal,
          );
      item.progress = 1;
      item.status = "done";
      // Let the owning view reflect the new file immediately (optimistic update)
      // instead of refetching the whole package after the batch.
      control.onUploaded?.(created);
      return true;
    } catch (err) {
      if (controller.signal.aborted) {
        item.status = "canceled";
      } else {
        item.status = "error";
        toast.error(
          `${item.name}: ${err instanceof ApiError ? err.message : "Upload failed"}`,
        );
      }
      return false;
    } finally {
      control.controllers[index] = null;
    }
  }

  /**
   * Upload `files` into a package with bounded concurrency, reporting per-file
   * progress. Files larger than `maxSize` are rejected up front with a toast.
   * Resolves to the number of files uploaded. Safe to fire and forget: the pool
   * keeps running (and its progress stays visible) even if the caller unmounts.
   */
  async function startUploads(
    packageId: number,
    files: File[],
    maxSize: number,
    packageName = "",
    onUploaded?: (file: PackageFile) => void,
  ): Promise<number> {
    if (isUploading(packageId).value || files.length === 0) {
      return 0;
    }
    const tooLarge = files.filter((file) => file.size > maxSize);
    const valid = files.filter((file) => file.size <= maxSize);
    if (tooLarge.length > 0) {
      const names = tooLarge.map((file) => file.name).join(", ");
      toast.error(
        `${names} exceed${tooLarge.length === 1 ? "s" : ""} the ${formatBytes(maxSize)} limit`,
      );
    }
    if (valid.length === 0) {
      return 0;
    }

    // Wrap in `reactive` before storing so mutations made through this
    // reference below flow through the proxy and stay reactive.
    const entry = reactive<PackageUpload>({
      items: valid.map((file) => ({
        id: (nextItemId += 1),
        name: file.name,
        progress: 0,
        status: "uploading",
      })),
      active: true,
      name: packageName,
    });
    uploadsByPackage.set(packageId, entry);
    controlByPackage.set(packageId, {
      files: valid,
      controllers: valid.map(() => null),
      canceled: new Set<number>(),
      onUploaded,
    });

    let uploaded = 0;
    let nextIndex = 0;
    // Bounded worker pool: each worker pulls the next queued file until the
    // batch is drained, so up to UPLOAD_CONCURRENCY uploads run at once while
    // per-file progress, cancel and retry keep operating on stable indices.
    async function worker(): Promise<void> {
      let index = nextIndex;
      nextIndex += 1;
      while (index < valid.length) {
        if (await uploadOne(packageId, index)) {
          uploaded += 1;
        }
        index = nextIndex;
        nextIndex += 1;
      }
    }
    try {
      const workerCount = Math.min(UPLOAD_CONCURRENCY, valid.length);
      await Promise.all(Array.from({ length: workerCount }, () => worker()));
      if (uploaded > 0) {
        toast.success(`Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"}`);
      }
    } finally {
      entry.active = false;
      // Keep the batch (with the failed/cancelled rows still visible) if
      // anything did not finish, so the user can retry or dismiss it.
      cleanup(packageId);
    }
    return uploaded;
  }

  /** Abort an in-flight or still-queued upload; it settles as "canceled". */
  function cancelUpload(packageId: number, index: number): void {
    const entry = uploadsByPackage.get(packageId);
    const control = controlByPackage.get(packageId);
    const item = entry?.items[index];
    if (!control || !item || item.status !== "uploading") {
      return;
    }
    const controller = control.controllers[index];
    if (controller) {
      controller.abort();
    } else {
      // Not started yet: mark it so the sequential loop skips it when reached.
      control.canceled.add(index);
      item.status = "canceled";
    }
  }

  /**
   * Retry a single failed or cancelled file. Resolves to whether it succeeded.
   * Only valid once the batch is idle; retrying flips `active` so a remounted
   * view still reacts to completion and the batch is cleaned up when all done.
   */
  async function retryUpload(packageId: number, index: number): Promise<boolean> {
    const entry = uploadsByPackage.get(packageId);
    const control = controlByPackage.get(packageId);
    const item = entry?.items[index];
    if (!entry || !control || !item || entry.active) {
      return false;
    }
    if (item.status === "uploading" || item.status === "done") {
      return false;
    }
    control.canceled.delete(index);
    entry.active = true;
    try {
      const ok = await uploadOne(packageId, index);
      if (ok) {
        toast.success(`Uploaded ${item.name}`);
      }
      return ok;
    } finally {
      entry.active = false;
      cleanup(packageId);
    }
  }

  /** Remove a finished (failed/cancelled) row the user does not want to retry. */
  function dismissUpload(packageId: number, index: number): void {
    const entry = uploadsByPackage.get(packageId);
    const control = controlByPackage.get(packageId);
    const item = entry?.items[index];
    if (!entry || !control || !item || entry.active || item.status === "uploading") {
      return;
    }
    entry.items.splice(index, 1);
    control.files.splice(index, 1);
    control.controllers.splice(index, 1);
    control.canceled.clear();
    if (entry.items.length === 0) {
      uploadsByPackage.delete(packageId);
      controlByPackage.delete(packageId);
    } else {
      cleanup(packageId);
    }
  }

  return {
    uploadsFor,
    isUploading,
    bindUploaded,
    startUploads,
    cancelUpload,
    retryUpload,
    dismissUpload,
    activeBatches,
    hasActiveUploads,
  };
}

