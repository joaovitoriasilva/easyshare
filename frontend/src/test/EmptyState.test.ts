import { defineComponent } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmptyState from "@/components/ui/EmptyState.vue";

const TestIcon = defineComponent({ template: "<svg data-test-icon />" });

describe("EmptyState", () => {
  it("renders semantic copy, an icon, and an action", () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: "No results",
        description: "Try another search.",
        icon: TestIcon,
        headingLevel: 2,
      },
      slots: { default: "<button>Clear search</button>" },
    });

    expect(wrapper.get("h2").text()).toBe("No results");
    expect(wrapper.text()).toContain("Try another search.");
    expect(wrapper.find("[data-test-icon]").exists()).toBe(true);
    expect(wrapper.get("button").text()).toBe("Clear search");
  });

  it("uses non-heading text by default", () => {
    const wrapper = mount(EmptyState, { props: { title: "Nothing here" } });

    expect(wrapper.get("p").text()).toBe("Nothing here");
    expect(wrapper.find("h1, h2, h3").exists()).toBe(false);
  });
});