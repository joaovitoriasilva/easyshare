<script setup lang="ts">
import { computed, type Component } from "vue";
import { cn } from "@/lib/utils";

const props = defineProps<{
  title: string;
  description?: string;
  icon?: Component;
  headingLevel?: 1 | 2 | 3;
  class?: string;
}>();

const titleTag = computed(() => props.headingLevel ? `h${props.headingLevel}` : "p");
</script>

<template>
  <div
    :class="cn(
      'flex min-h-48 flex-col items-center justify-center rounded-md border border-dashed px-5 py-10 text-center',
      props.class,
    )"
  >
    <span
      v-if="icon"
      class="mb-4 flex h-10 w-10 items-center justify-center rounded-md border bg-card text-muted-foreground"
    >
      <component :is="icon" class="h-5 w-5" aria-hidden="true" />
    </span>
    <component :is="titleTag" class="font-medium text-foreground">{{ title }}</component>
    <p v-if="description" class="mt-1 max-w-md text-sm text-muted-foreground">
      {{ description }}
    </p>
    <div v-if="$slots.default" class="mt-5 flex flex-wrap justify-center gap-2">
      <slot />
    </div>
  </div>
</template>