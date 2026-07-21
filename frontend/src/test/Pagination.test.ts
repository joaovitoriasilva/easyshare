import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Pagination from "@/components/ui/Pagination.vue";

describe("Pagination", () => {
  it("marks the current page with aria-current", () => {
    const wrapper = mount(Pagination, {
      props: { total: 30, limit: 10, offset: 0 },
    });
    expect(wrapper.get('[aria-current="page"]').text()).toBe("1");
  });

  it("emits update:offset with the target page's byte offset", async () => {
    const wrapper = mount(Pagination, {
      props: { total: 30, limit: 10, offset: 0 },
    });
    await wrapper.get('[aria-label="Page 3"]').trigger("click");
    expect(wrapper.emitted("update:offset")?.[0]).toEqual([20]);
  });

  it("does not emit when the current page is clicked", async () => {
    const wrapper = mount(Pagination, {
      props: { total: 30, limit: 10, offset: 0 },
    });
    await wrapper.get('[aria-current="page"]').trigger("click");
    expect(wrapper.emitted("update:offset")).toBeUndefined();
  });

  it("disables Previous on the first page and Next on the last", () => {
    const first = mount(Pagination, { props: { total: 30, limit: 10, offset: 0 } });
    expect(
      first.get('[aria-label="Previous page"]').attributes("disabled"),
    ).toBeDefined();

    const last = mount(Pagination, { props: { total: 30, limit: 10, offset: 20 } });
    expect(
      last.get('[aria-label="Next page"]').attributes("disabled"),
    ).toBeDefined();
  });

  it("collapses long ranges with an ellipsis but always shows first and last", () => {
    // Page 10 of 20.
    const wrapper = mount(Pagination, {
      props: { total: 200, limit: 10, offset: 90 },
    });
    expect(wrapper.text()).toContain("…");
    expect(wrapper.find('[aria-label="Page 1"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Page 20"]').exists()).toBe(true);
  });

  it("disables every control when the disabled prop is set", () => {
    const wrapper = mount(Pagination, {
      props: { total: 30, limit: 10, offset: 10, disabled: true },
    });
    expect(
      wrapper.get('[aria-label="Next page"]').attributes("disabled"),
    ).toBeDefined();
    expect(
      wrapper.get('[aria-label="Previous page"]').attributes("disabled"),
    ).toBeDefined();
  });
});
