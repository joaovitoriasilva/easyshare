import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useToastStore } from "@/stores/toast";

describe("toast store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("adds a toast with the given variant, title and description", () => {
    const toast = useToastStore();
    toast.success("Saved", { description: "All good" });
    expect(toast.toasts).toHaveLength(1);
    expect(toast.toasts[0]).toMatchObject({
      variant: "success",
      title: "Saved",
      description: "All good",
    });
  });

  it("auto-dismisses after the duration elapses", () => {
    const toast = useToastStore();
    toast.info("Heads up", { duration: 1000 });
    expect(toast.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(toast.toasts).toHaveLength(0);
  });

  it("keeps a toast with duration 0 until dismissed manually", () => {
    const toast = useToastStore();
    const id = toast.error("Persistent", { duration: 0 });
    vi.advanceTimersByTime(60000);
    expect(toast.toasts).toHaveLength(1);
    toast.dismiss(id);
    expect(toast.toasts).toHaveLength(0);
  });

  it("gives errors a longer default duration than other variants", () => {
    const toast = useToastStore();
    toast.success("ok");
    toast.error("bad");
    const [success, error] = toast.toasts;
    expect(error.duration).toBeGreaterThan(success.duration);
  });

  it("pauses and resumes the auto-dismiss timer", () => {
    const toast = useToastStore();
    const id = toast.info("Hover me", { duration: 1000 });
    vi.advanceTimersByTime(600);
    toast.pause(id);
    vi.advanceTimersByTime(5000);
    expect(toast.toasts).toHaveLength(1);
    toast.resume(id);
    vi.advanceTimersByTime(399);
    expect(toast.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toast.toasts).toHaveLength(0);
  });
});
