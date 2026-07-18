import { computed, reactive, type ComputedRef } from "vue";
import { packagesApi } from "@/api";
import { ApiError } from "@/api/client";
import { useToasts } from "@/composables/useToasts";
import { formatBytes } from "@/lib/format";

/** A single file's progress within an in-flight upload batch. */
export interface UploadItem {
  name: string;
  progress: number;
  status: "uploading" | "done" | "error";
}

interface PackageUpload {
  items: UploadItem[];
  active: boolean;
}

/**
 * In-flight uploads keyed by package id. Module-level (like `useToasts`) so an
 * upload's progress survives navigating away from a package and back: the view
 * is unmounted and remounted, but the state and the running upload loop live
 * here rather than inside the component.
 */
const uploadsByPackage = reactive(new Map<number, PackageUpload>());

const EMPTY: UploadItem[] = [];

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
      items: valid.map((file) => ({ name: file.name, progress: 0, status: "uploading" })),
      active: true,
    });
    uploadsByPackage.set(packageId, entry);

    let uploaded = 0;
    try {
      for (let index = 0; index < valid.length; index += 1) {
        const item = entry.items[index];
        try {
          await packagesApi.uploadFile(packageId, valid[index], (fraction) => {
            item.progress = fraction;
          });
          item.progress = 1;
          item.status = "done";
          uploaded += 1;
        } catch (err) {
          item.status = "error";
          toast.error(
            `${item.name}: ${err instanceof ApiError ? err.message : "Upload failed"}`,
          );
        }
      }
      if (uploaded > 0) {
        toast.success(`Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"}`);
      }
    } finally {
      entry.active = false;
      // Drop the batch once everything succeeded; keep it (with the failed rows
      // still visible) if anything failed so the user can see what went wrong.
      if (entry.items.every((item) => item.status === "done")) {
        uploadsByPackage.delete(packageId);
      }
    }
    return uploaded;
  }

  return { uploadsFor, isUploading, startUploads };
}
