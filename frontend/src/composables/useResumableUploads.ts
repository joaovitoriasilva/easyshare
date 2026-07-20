import { ref } from "vue";
import { api } from "@/api/client";
import type { UploadSession } from "@/api/types";
import {
  discardResumableUpload,
  listResumableUploads,
  type ResumableUpload,
} from "@/lib/chunkedUpload";

/** A resumable upload plus the server's current received offset. */
export interface PendingResume extends ResumableUpload {
  offset: number;
}

/**
 * Surfaces resumable (interrupted) uploads for a package after a full page
 * reload.
 *
 * The chunked-upload flow persists a session id in localStorage keyed by a
 * stable file signature. After a reload the module-level upload state is gone,
 * but the server-side session (and its received offset) survives. This
 * composable reconciles the two so a view can offer to resume or discard each
 * interrupted upload — resuming still requires the user to re-select the file,
 * since the browser cannot read the original `File` back after a reload.
 */
export function useResumableUploads(packageId: number) {
  const pending = ref<PendingResume[]>([]);

  /** Reload the list, fetching each session's offset and pruning dead ones. */
  async function refresh(): Promise<void> {
    const resolved = await Promise.all(
      listResumableUploads(packageId).map(
        async (candidate): Promise<PendingResume | null> => {
          try {
            const status = await api.request<UploadSession>(
              `/packages/${packageId}/uploads/${candidate.uploadId}`,
            );
            // A finished session isn't worth surfacing; forget it.
            if (status.complete) {
              void discardResumableUpload(packageId, candidate);
              return null;
            }
            return {
              ...candidate,
              offset: Math.min(status.offset, candidate.size),
            };
          } catch {
            // Session pruned/expired server-side: drop the stale local entry.
            localStorage.removeItem(candidate.key);
            return null;
          }
        },
      ),
    );
    pending.value = resolved.filter(
      (entry): entry is PendingResume => entry !== null,
    );
  }

  /** Drop a handled entry from the list without touching the server session. */
  function remove(key: string): void {
    pending.value = pending.value.filter((entry) => entry.key !== key);
  }

  /** Abort and forget an interrupted upload. */
  async function discard(entry: PendingResume): Promise<void> {
    remove(entry.key);
    await discardResumableUpload(packageId, entry);
  }

  return { pending, refresh, remove, discard };
}
