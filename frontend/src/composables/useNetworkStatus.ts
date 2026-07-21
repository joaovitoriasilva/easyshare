import { readonly, ref } from "vue";

/**
 * Reactive online/offline state driven by the browser's network events.
 *
 * Module-level so every caller shares the same flag and the `online`/`offline`
 * listeners are registered exactly once. Used to surface a banner (and let
 * views react) when connectivity drops, instead of only failing requests with a
 * generic network error.
 */
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
let initialized = false;

function ensureListeners(): void {
  if (initialized || typeof window === "undefined") {
    return;
  }
  initialized = true;
  window.addEventListener("online", () => {
    online.value = true;
  });
  window.addEventListener("offline", () => {
    online.value = false;
  });
}

/** Reactive, read-only `online` flag reflecting the browser's connectivity. */
export function useNetworkStatus() {
  ensureListeners();
  return { online: readonly(online) };
}
