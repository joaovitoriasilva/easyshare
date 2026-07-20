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

/** Stable key for a file so an interrupted upload can be resumed after reload. */
function resumeKey(packageId: number, file: File): string {
  return `${RESUME_PREFIX}${packageId}:${file.name}:${file.size}:${file.lastModified}`;
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
  let uploadId = localStorage.getItem(key);
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
    localStorage.setItem(key, uploadId);
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
