import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "@/composables/useToasts";

describe("useToasts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Module-level state persists between tests; clear any leftovers.
    const { toasts, dismiss } = useToasts();
    for (const toast of [...toasts.value]) {
      dismiss(toast.id);
    }
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("adds a toast with the given kind and message", () => {
    const { toasts, success } = useToasts();
    success("Saved");
    expect(toasts.value).toHaveLength(1);
    expect(toasts.value[0]).toMatchObject({ kind: "success", message: "Saved" });
  });

  it("auto-dismisses after the duration elapses", () => {
    const { toasts, info } = useToasts();
    info("Heads up", 1000);
    expect(toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(toasts.value).toHaveLength(0);
  });

  it("keeps a toast with duration 0 until dismissed manually", () => {
    const { toasts, error, dismiss } = useToasts();
    const id = error("Persistent", 0);
    vi.advanceTimersByTime(60000);
    expect(toasts.value).toHaveLength(1);
    dismiss(id);
    expect(toasts.value).toHaveLength(0);
  });

  it("dispatches all four severities", () => {
    const { toasts, success, error, warning, info } = useToasts();
    success("a", 0);
    error("b", 0);
    warning("c", 0);
    info("d", 0);
    expect(toasts.value.map((toast) => toast.kind)).toEqual([
      "success",
      "error",
      "warning",
      "info",
    ]);
  });
});
