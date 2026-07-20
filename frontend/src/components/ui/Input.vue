<script setup lang="ts">
import { computed } from "vue";
import { cn } from "@/lib/utils";

const props = defineProps<{
  modelValue?: string | number;
  type?: string;
  placeholder?: string;
  class?: string;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const model = computed({
  get: () => props.modelValue ?? "",
  // A native <input type="number"> makes Vue's v-model coerce the value to a
  // number; stringify so the emitted model always matches the declared
  // `string` contract and consumers can safely call string methods on it.
  set: (value: string | number) => emit("update:modelValue", String(value)),
});
</script>

<template>
  <input
    v-model="model"
    :type="type ?? 'text'"
    :placeholder="placeholder"
    :class="
      cn(
        'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive',
        props.class,
      )
    "
  />
</template>
