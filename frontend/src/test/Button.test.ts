import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Button from "@/components/ui/Button.vue";

describe("Button", () => {
  it("renders slot content", () => {
    const wrapper = mount(Button, { slots: { default: "Click me" } });
    expect(wrapper.text()).toBe("Click me");
  });

  it("applies destructive variant classes", () => {
    const wrapper = mount(Button, {
      props: { variant: "destructive" },
      slots: { default: "Delete" },
    });
    expect(wrapper.classes().join(" ")).toContain("bg-destructive");
  });

  it("emits click events", async () => {
    const wrapper = mount(Button, { slots: { default: "Go" } });
    await wrapper.trigger("click");
    expect(wrapper.emitted("click")).toHaveLength(1);
  });
});
