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

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData | URLSearchParams;
  auth?: boolean;
  /** Request timeout in ms; `0` disables it. Defaults to 30s (0 for uploads). */
  timeout?: number;
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

export const api = { request };
