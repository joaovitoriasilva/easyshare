<script setup lang="ts">
import { CheckboxIndicator, CheckboxRoot } from "reka-ui";
import { Check } from "lucide-vue-next";
import { cn } from "@/lib/utils";

const props = defineProps<{ modelValue?: boolean; class?: string }>();
const emit = defineEmits<{ (event: "update:modelValue", value: boolean): void }>();
</script>

<template>
  <CheckboxRoot
    :model-value="props.modelValue"
    :class="
      cn(
        'peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground',
        props.class,
      )
    "
    @update:model-value="(value) => emit('update:modelValue', value === true)"
  >
    <CheckboxIndicator class="flex items-center justify-center text-current">
      <Check class="h-3.5 w-3.5" />
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
