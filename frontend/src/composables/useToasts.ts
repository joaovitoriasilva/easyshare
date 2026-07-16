import { readonly, ref } from "vue";
import type { Severity } from "@/lib/severity";

/** A transient toast notification. */
export interface Toast {
  id: number;
  kind: Severity;
  message: string;
}

const DEFAULT_DURATION_MS = 5000;

const toasts = ref<Toast[]>([]);
let nextId = 0;

/**
 * App-wide toast notifications. Module-level state means any layer (views,
 * stores, the API client, a global error handler) can surface feedback without
 * prop drilling, while a single Toaster renders the list in one host.
 */
export function useToasts() {
  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  /** Queues a toast, auto-dismissing after `duration` unless it is 0. */
  function notify(kind: Severity, message: string, duration = DEFAULT_DURATION_MS): number {
    nextId += 1;
    const id = nextId;
    toasts.value = [...toasts.value, { id, kind, message }];
    if (duration > 0) {
      window.setTimeout(() => dismiss(id), duration);
    }
    return id;
  }

  return {
    toasts: readonly(toasts),
    notify,
    dismiss,
    success: (message: string, duration?: number) => notify("success", message, duration),
    error: (message: string, duration?: number) => notify("error", message, duration),
    info: (message: string, duration?: number) => notify("info", message, duration),
    warning: (message: string, duration?: number) => notify("warning", message, duration),
  };
}
