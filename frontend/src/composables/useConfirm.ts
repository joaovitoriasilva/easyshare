import { readonly, ref } from "vue";

export interface ConfirmOptions {
  message: string;
  title?: string;
  confirmText?: string;
  cancelText?: string;
  /** Styles the confirm button as destructive (red). */
  destructive?: boolean;
}

interface ConfirmState extends Required<ConfirmOptions> {
  open: boolean;
}

const state = ref<ConfirmState>({
  open: false,
  title: "Are you sure?",
  message: "",
  confirmText: "Confirm",
  cancelText: "Cancel",
  destructive: false,
});

let resolver: ((confirmed: boolean) => void) | null = null;

/**
 * Promise-based confirmation dialog backed by module-level state, so any view
 * can `await confirm(...)` before a destructive action while a single
 * ConfirmDialog renders the prompt in one host.
 */
export function useConfirm() {
  function settle(confirmed: boolean): void {
    state.value = { ...state.value, open: false };
    resolver?.(confirmed);
    resolver = null;
  }

  function confirm(options: ConfirmOptions): Promise<boolean> {
    // Resolve any prompt already open (superseded) as cancelled.
    resolver?.(false);
    state.value = {
      open: true,
      title: options.title ?? "Are you sure?",
      message: options.message,
      confirmText: options.confirmText ?? "Confirm",
      cancelText: options.cancelText ?? "Cancel",
      destructive: options.destructive ?? false,
    };
    return new Promise<boolean>((resolve) => {
      resolver = resolve;
    });
  }

  return {
    state: readonly(state),
    confirm,
    accept: () => settle(true),
    cancel: () => settle(false),
  };
}
