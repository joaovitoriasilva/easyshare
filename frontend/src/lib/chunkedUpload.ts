/**
 * Resumable, chunked file upload.
 *
 * A large file is uploaded as consecutive byte ranges to a server-side session,
 * so a dropped connection or a page reload resumes from the last acknowledged
 * offset instead of restarting. The session id is remembered in `localStorage`
 * keyed by a stable file signature, and each chunk is sent with an XHR so its
 * upload progress is reported at byte granularity.
 */

import { api, ApiError, buildApiError, getToken } from "@/api/client";
import type { PackageFile, UploadSession } from "@/api/types";

const RESUME_PREFIX = "easyshare_upload:";

/** Metadata persisted per in-progress upload so it can be found after a reload. */
export interface StoredUploadSession {
  uploadId: string;
  filename: string;
  size: number;
  lastModified: number;
}

/** A resumable upload discovered in localStorage for a package. */
export interface ResumableUpload extends StoredUploadSession {
  /** The localStorage key backing this entry, used to discard it. */
  key: string;
  packageId: number;
}

/** Stable key for a file so an interrupted upload can be resumed after reload. */
function resumeKey(packageId: number, file: File): string {
  return `${RESUME_PREFIX}${packageId}:${file.name}:${file.size}:${file.lastModified}`;
}

/** Read (and validate) the stored session at `key`, pruning a corrupt entry. */
function readStoredSession(key: string): StoredUploadSession | null {
  const raw = localStorage.getItem(key);
  if (!raw) {
    return null;
  }
  try {
    const data = JSON.parse(raw) as Partial<StoredUploadSession>;
    if (typeof data.uploadId === "string" && data.uploadId) {
      return {
        uploadId: data.uploadId,
        filename: typeof data.filename === "string" ? data.filename : "",
        size: typeof data.size === "number" ? data.size : 0,
        lastModified: typeof data.lastModified === "number" ? data.lastModified : 0,
      };
    }
  } catch {
    /* corrupt or legacy value: fall through and drop it */
  }
  localStorage.removeItem(key);
  return null;
}

/** Persist a stored session as JSON so it survives a full page reload. */
function writeStoredSession(key: string, session: StoredUploadSession): void {
  localStorage.setItem(key, JSON.stringify(session));
}

export interface ChunkedUploadOptions {
  /** Bytes per chunk (advertised by the server). */
  chunkSize: number;
  /** Reports the overall upload fraction (0..1). */
  onProgress?: (fraction: number) => void;
  /** Aborts the upload; the returned promise rejects as "Upload canceled". */
  signal?: AbortSignal;
}

interface ChunkResult {
  conflict: boolean;
  resumeOffset: number;
  body: UploadSession | null;
}

/** PATCH one chunk via XHR so upload progress events are available. */
function patchChunk(
  path: string,
  chunk: Blob,
  offset: number,
  onLoaded: (loaded: number) => void,
  signal?: AbortSignal,
): Promise<ChunkResult> {
  return new Promise<ChunkResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PATCH", `/api${path}`);
    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", "Bearer " + token);
    }
    xhr.setRequestHeader("Content-Type", "application/offset+octet-stream");
    xhr.setRequestHeader("Upload-Offset", String(offset));

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onLoaded(event.loaded);
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const body = xhr.responseText
          ? (JSON.parse(xhr.responseText) as UploadSession)
          : null;
        resolve({ conflict: false, resumeOffset: offset, body });
        return;
      }
      if (xhr.status === 409) {
        // The server tells us where to resume from.
        const header = Number(xhr.getResponseHeader("Upload-Offset"));
        resolve({
          conflict: true,
          resumeOffset: Number.isFinite(header) ? header : offset,
          body: null,
        });
        return;
      }
      if (xhr.status === 401) {
        // Mirror the client's global handling for an expired session.
        reject(buildApiError(401, xhr.statusText, xhr.responseText || null));
        return;
      }
      reject(buildApiError(xhr.status, xhr.statusText, xhr.responseText || null));
    });
    xhr.addEventListener("error", () =>
      reject(new ApiError(0, "Network error. Please check your connection.")),
    );
    xhr.addEventListener("abort", () => reject(new ApiError(0, "Upload canceled")));

    if (signal) {
      if (signal.aborted) {
        reject(new ApiError(0, "Upload canceled"));
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(chunk);
  });
}

/**
 * Upload a file in resumable chunks and resolve with the created package file.
 * Reuses a stored session (resuming from its current offset) when one exists for
 * this exact file, otherwise opens a new one.
 */
export async function uploadFileChunked(
  packageId: number,
  file: File,
  options: ChunkedUploadOptions,
): Promise<PackageFile> {
  const key = resumeKey(packageId, file);
  const total = file.size;
  let uploadId = readStoredSession(key)?.uploadId ?? null;
  let offset = 0;

  // Try to resume a previously-opened session for this file.
  if (uploadId) {
    try {
      const status = await api.request<UploadSession>(
        `/packages/${packageId}/uploads/${uploadId}`,
      );
      offset = Math.min(status.offset, total);
    } catch {
      uploadId = null;
      localStorage.removeItem(key);
    }
  }

  if (!uploadId) {
    const created = await api.request<UploadSession>(
      `/packages/${packageId}/uploads`,
      {
        method: "POST",
        body: {
          filename: file.name,
          size: total,
          content_type: file.type || "application/octet-stream",
        },
      },
    );
    uploadId = created.upload_id;
    offset = created.offset;
    writeStoredSession(key, {
      uploadId,
      filename: file.name,
      size: file.size,
      lastModified: file.lastModified,
    });
  }

  const chunkSize = Math.max(1, options.chunkSize);
  const report = (): void => options.onProgress?.(total > 0 ? offset / total : 1);
  report();

  // Loop until the server reports completion. The `total === 0` guard sends a
  // single empty chunk so a zero-byte file still finalises.
  for (;;) {
    if (options.signal?.aborted) {
      throw new ApiError(0, "Upload canceled");
    }
    const end = Math.min(offset + chunkSize, total);
    const chunkStart = offset;
    const result = await patchChunk(
      `/packages/${packageId}/uploads/${uploadId}`,
      file.slice(chunkStart, end),
      chunkStart,
      (loaded) => options.onProgress?.(total > 0 ? (chunkStart + loaded) / total : 0),
      options.signal,
    );

    if (result.conflict) {
      offset = Math.min(result.resumeOffset, total);
      continue;
    }
    const body = result.body;
    offset = body?.offset ?? end;
    report();
    if (body?.complete && body.file) {
      localStorage.removeItem(key);
      return body.file;
    }
    if (total === 0) {
      // A zero-byte file that didn't finalise on its empty chunk is unexpected.
      break;
    }
  }

  localStorage.removeItem(key);
  throw new ApiError(0, "Upload did not complete");
}

/**
 * List uploads that were interrupted (their session is still in localStorage)
 * for a package, so a view can offer to resume them after a full page reload.
 */
export function listResumableUploads(packageId: number): ResumableUpload[] {
  const prefix = `${RESUME_PREFIX}${packageId}:`;
  // Collect keys first: `readStoredSession` may prune a corrupt entry, which
  // would shift indices if we read by index in the same loop.
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (key && key.startsWith(prefix)) {
      keys.push(key);
    }
  }
  const found: ResumableUpload[] = [];
  for (const key of keys) {
    const stored = readStoredSession(key);
    if (stored) {
      found.push({ ...stored, key, packageId });
    }
  }
  return found;
}

/**
 * Forget a resumable upload: drop its localStorage entry and best-effort abort
 * the server-side session so its scratch file is freed immediately instead of
 * waiting for the background TTL sweep. A missing/expired session is ignored.
 */
export async function discardResumableUpload(
  packageId: number,
  upload: { key: string; uploadId: string },
): Promise<void> {
  localStorage.removeItem(upload.key);
  try {
    await api.request<void>(`/packages/${packageId}/uploads/${upload.uploadId}`, {
      method: "DELETE",
    });
  } catch {
    /* the background sweep removes an abandoned session eventually */
  }
}
