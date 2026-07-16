import { defineStore } from "pinia";
import { ref } from "vue";

/** Visual + semantic category for a toast notification. */
export type ToastVariant = "success" | "error" | "warning" | "info";

/** A notification rendered by the global Toaster. */
export interface Toast {
  id: number;
  variant: ToastVariant;
  title: string;
  description?: string;
  /** Auto-dismiss delay in ms; 0 keeps the toast until dismissed manually. */
  duration: number;
}

export interface ToastOptions {
  description?: string;
  duration?: number;
}

const DEFAULT_DURATION = 5000;
const ERROR_DURATION = 8000;

interface Timer {
  handle: ReturnType<typeof setTimeout>;
  remaining: number;
  startedAt: number;
}

export const useToastStore = defineStore("toast", () => {
  const toasts = ref<Toast[]>([]);
  const timers = new Map<number, Timer>();
  let nextId = 0;

  function schedule(id: number, remaining: number): void {
    if (remaining <= 0) {
      return;
    }
    timers.set(id, {
      handle: setTimeout(() => dismiss(id), remaining),
      remaining,
      startedAt: Date.now(),
    });
  }

  function dismiss(id: number): void {
    const timer = timers.get(id);
    if (timer) {
      clearTimeout(timer.handle);
      timers.delete(id);
    }
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  /** Pause a toast's auto-dismiss timer, e.g. while it is hovered. */
  function pause(id: number): void {
    const timer = timers.get(id);
    if (!timer) {
      return;
    }
    clearTimeout(timer.handle);
    timer.remaining -= Date.now() - timer.startedAt;
  }

  /** Resume a previously paused auto-dismiss timer. */
  function resume(id: number): void {
    const timer = timers.get(id);
    if (!timer) {
      return;
    }
    if (timer.remaining <= 0) {
      dismiss(id);
      return;
    }
    schedule(id, timer.remaining);
  }

  function add(variant: ToastVariant, title: string, options: ToastOptions = {}): number {
    const id = nextId++;
    const duration =
      options.duration ?? (variant === "error" ? ERROR_DURATION : DEFAULT_DURATION);
    toasts.value = [
      ...toasts.value,
      { id, variant, title, description: options.description, duration },
    ];
    schedule(id, duration);
    return id;
  }

  const success = (title: string, options?: ToastOptions): number =>
    add("success", title, options);
  const error = (title: string, options?: ToastOptions): number =>
    add("error", title, options);
  const warning = (title: string, options?: ToastOptions): number =>
    add("warning", title, options);
  const info = (title: string, options?: ToastOptions): number =>
    add("info", title, options);

  return { toasts, add, dismiss, pause, resume, success, error, warning, info };
});
