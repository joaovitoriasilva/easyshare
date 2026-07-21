<script setup lang="ts">
import { computed } from "vue";
import { ChevronLeft, ChevronRight } from "@lucide/vue";
import Button from "./Button.vue";

/**
 * Offset/limit pagination control with numbered pages.
 *
 * Renders Previous / page-number / Next buttons for the standard
 * ``{ total, limit, offset }`` shape every list endpoint returns, emitting the
 * new byte offset via ``update:offset`` so a parent can `v-model:offset` it (and
 * refetch). Long ranges are collapsed with ellipsis gaps so the control stays
 * compact — always showing the first, last and current-adjacent pages — and the
 * current page is marked with ``aria-current`` for assistive tech.
 */
const props = withDefaults(
  defineProps<{
    total: number;
    limit: number;
    offset: number;
    /** Optional summary shown alongside the controls, e.g. "12 packages". */
    label?: string;
    /** Disable the controls (e.g. while a page is being fetched). */
    disabled?: boolean;
  }>(),
  { label: "", disabled: false },
);

const emit = defineEmits<{ (event: "update:offset", value: number): void }>();

const pageCount = computed(() =>
  Math.max(1, Math.ceil(props.total / Math.max(1, props.limit))),
);
const currentPage = computed(() =>
  Math.min(pageCount.value, Math.floor(props.offset / Math.max(1, props.limit)) + 1),
);

/** Page tokens to render: numbers plus "gap" markers, e.g. 1 … 4 5 6 … 20. */
const pages = computed<(number | "gap")[]>(() => {
  const last = pageCount.value;
  const current = currentPage.value;
  const wanted = new Set<number>([1, last, current, current - 1, current + 1]);
  const shown = [...wanted]
    .filter((page) => page >= 1 && page <= last)
    .sort((a, b) => a - b);
  const tokens: (number | "gap")[] = [];
  let previous = 0;
  for (const page of shown) {
    if (previous && page - previous > 1) {
      tokens.push("gap");
    }
    tokens.push(page);
    previous = page;
  }
  return tokens;
});

function goToPage(page: number): void {
  const clamped = Math.min(pageCount.value, Math.max(1, page));
  const nextOffset = (clamped - 1) * props.limit;
  if (nextOffset !== props.offset) {
    emit("update:offset", nextOffset);
  }
}
</script>

<template>
  <nav
    aria-label="Pagination"
    class="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between"
  >
    <span v-if="label">{{ label }}</span>
    <div class="flex items-center gap-1">
      <Button
        variant="outline"
        size="sm"
        :disabled="disabled || currentPage <= 1"
        aria-label="Previous page"
        @click="goToPage(currentPage - 1)"
      >
        <ChevronLeft class="h-4 w-4" />
        <span class="hidden sm:inline">Previous</span>
      </Button>
      <template v-for="(token, index) in pages" :key="index">
        <span v-if="token === 'gap'" class="px-1 tabular-nums" aria-hidden="true">…</span>
        <Button
          v-else
          :variant="token === currentPage ? 'default' : 'outline'"
          size="sm"
          class="min-w-9 tabular-nums"
          :disabled="disabled"
          :aria-label="`Page ${token}`"
          :aria-current="token === currentPage ? 'page' : undefined"
          @click="goToPage(token)"
        >
          {{ token }}
        </Button>
      </template>
      <Button
        variant="outline"
        size="sm"
        :disabled="disabled || currentPage >= pageCount"
        aria-label="Next page"
        @click="goToPage(currentPage + 1)"
      >
        <span class="hidden sm:inline">Next</span>
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>
  </nav>
</template>
