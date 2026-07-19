/** Thin, typed wrapper around the EasyShare REST API. */

const TOKEN_KEY = "easyshare_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * Register a callback invoked when an authenticated request is rejected with
 * 401 (typically an expired token), so the app can clear the session and send
 * the user to the login screen instead of surfacing a scattered per-view error.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData | URLSearchParams;
  auth?: boolean;
  /** Request timeout in ms; `0` disables it. Defaults to 30s (0 for uploads). */
  timeout?: number;
  /** Skip the global 401 handler (used by the current-user probe on startup). */
  skipAuthRedirect?: boolean;
}

/** Default per-request timeout; uploads opt out so large files aren't cut off. */
const DEFAULT_TIMEOUT_MS = 30_000;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const init: RequestInit = { method: options.method ?? "GET" };

  if (options.auth !== false) {
    const token = getToken();
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
  }

  if (options.form) {
    init.body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  init.headers = headers;

  // Fail fast on a hung backend, but never time out (potentially large) uploads.
  const isUpload = options.form instanceof FormData;
  const timeout = options.timeout ?? (isUpload ? 0 : DEFAULT_TIMEOUT_MS);
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  if (timeout > 0) {
    timer = setTimeout(
      () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
      timeout,
    );
    init.signal = controller.signal;
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch (error) {
    if (
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError")
    ) {
      throw new ApiError(0, "The request timed out. Please try again.");
    }
    throw new ApiError(0, "Network error. Please check your connection.");
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }

  if (!response.ok) {
    let message = response.statusText;
    let detail: unknown = null;
    try {
      const data: unknown = await response.json();
      if (data && typeof data === "object" && "detail" in data) {
        detail = (data as { detail: unknown }).detail;
        if (typeof detail === "string") {
          message = detail;
        }
      } else {
        detail = data;
      }
    } catch {
      /* ignore body parse errors */
    }
    if (
      response.status === 401 &&
      options.auth !== false &&
      !options.skipAuthRedirect
    ) {
      unauthorizedHandler?.();
    }
    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.blob()) as T;
}

export interface UploadOptions {
  /** Called with the upload fraction (0..1) as the file streams to the server. */
  onProgress?: (fraction: number) => void;
  /** Aborts the in-flight upload when signalled; it rejects as "Upload canceled". */
  signal?: AbortSignal;
}

/**
 * Upload a single file with progress reporting. Uses XMLHttpRequest because the
 * fetch API cannot report upload progress; auth, error shaping and the global
 * 401 handler mirror `request()`. There is no timeout so large uploads are not
 * cut off.
 */
function upload<T>(path: string, file: File, options: UploadOptions = {}): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);

    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", "Bearer " + token);
    }

    if (options.onProgress) {
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          options.onProgress?.(event.loaded / event.total);
        }
      });
    }

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(
            xhr.responseText ? (JSON.parse(xhr.responseText) as T) : (undefined as T),
          );
        } catch {
          resolve(undefined as T);
        }
        return;
      }
      let message = xhr.statusText;
      let detail: unknown = null;
      try {
        const data: unknown = JSON.parse(xhr.responseText);
        if (data && typeof data === "object" && "detail" in data) {
          detail = (data as { detail: unknown }).detail;
          if (typeof detail === "string") {
            message = detail;
          }
        } else {
          detail = data;
        }
      } catch {
        /* ignore body parse errors */
      }
      if (xhr.status === 401) {
        unauthorizedHandler?.();
      }
      reject(new ApiError(xhr.status, message, detail));
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError(0, "Network error. Please check your connection.")),
    );

    xhr.addEventListener("abort", () => reject(new ApiError(0, "Upload canceled")));

    if (options.signal) {
      if (options.signal.aborted) {
        reject(new ApiError(0, "Upload canceled"));
        return;
      }
      options.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = { request, upload };
