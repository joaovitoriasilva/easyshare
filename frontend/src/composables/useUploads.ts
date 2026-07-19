import { computed, reactive, type ComputedRef } from "vue";
import { packagesApi } from "@/api";
import { ApiError } from "@/api/client";
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
}

/**
 * In-flight uploads keyed by package id. Module-level (like `useToasts`) so an
 * upload's progress survives navigating away from a package and back: the view
 * is unmounted and remounted, but the state and the running upload loop live
 * here rather than inside the component.
 */
const uploadsByPackage = reactive(new Map<number, PackageUpload>());
const controlByPackage = new Map<number, UploadControl>();

const EMPTY: UploadItem[] = [];
let nextItemId = 0;

export function useUploads() {
  const toast = useToasts();

  /** Reactive list of the current upload batch for a package (empty if none). */
  function uploadsFor(packageId: number): ComputedRef<UploadItem[]> {
    return computed(() => uploadsByPackage.get(packageId)?.items ?? EMPTY);
  }

  /** Whether a package currently has an upload batch in progress. */
  function isUploading(packageId: number): ComputedRef<boolean> {
    return computed(() => uploadsByPackage.get(packageId)?.active ?? false);
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
      await packagesApi.uploadFile(
        packageId,
        control.files[index],
        (fraction) => {
          item.progress = fraction;
        },
        controller.signal,
      );
      item.progress = 1;
      item.status = "done";
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
   * Upload `files` into a package sequentially, reporting per-file progress.
   * Files larger than `maxSize` are rejected up front with a toast. Resolves to
   * the number of files uploaded. Safe to fire and forget: the loop keeps
   * running (and its progress stays visible) even if the caller unmounts.
   */
  async function startUploads(
    packageId: number,
    files: File[],
    maxSize: number,
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
    });
    uploadsByPackage.set(packageId, entry);
    controlByPackage.set(packageId, {
      files: valid,
      controllers: valid.map(() => null),
      canceled: new Set<number>(),
    });

    let uploaded = 0;
    try {
      for (let index = 0; index < valid.length; index += 1) {
        if (await uploadOne(packageId, index)) {
          uploaded += 1;
        }
      }
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
    startUploads,
    cancelUpload,
    retryUpload,
    dismissUpload,
  };
}

