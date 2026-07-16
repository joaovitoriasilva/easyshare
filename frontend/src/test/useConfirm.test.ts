import { describe, expect, it } from "vitest";
import { useConfirm } from "@/composables/useConfirm";

describe("useConfirm", () => {
  it("opens with the given options and resolves true on accept", async () => {
    const { confirm, accept, state } = useConfirm();
    const pending = confirm({
      message: "Delete it?",
      confirmText: "Delete",
      destructive: true,
    });
    expect(state.value.open).toBe(true);
    expect(state.value.message).toBe("Delete it?");
    expect(state.value.confirmText).toBe("Delete");
    expect(state.value.destructive).toBe(true);
    accept();
    await expect(pending).resolves.toBe(true);
    expect(state.value.open).toBe(false);
  });

  it("resolves false on cancel", async () => {
    const { confirm, cancel, state } = useConfirm();
    const pending = confirm({ message: "Sure?" });
    cancel();
    await expect(pending).resolves.toBe(false);
    expect(state.value.open).toBe(false);
  });

  it("supersedes an open prompt, resolving the previous as cancelled", async () => {
    const { confirm, accept } = useConfirm();
    const first = confirm({ message: "First" });
    const second = confirm({ message: "Second" });
    await expect(first).resolves.toBe(false);
    accept();
    await expect(second).resolves.toBe(true);
  });
});
