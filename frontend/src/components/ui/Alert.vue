<script setup lang="ts">
import { severityClasses, severityIcons, type Severity } from "@/lib/severity";
import { cn } from "@/lib/utils";

const props = defineProps<{ kind: Severity; class?: string }>();
</script>

<template>
  <div
    :class="
      cn(
        'flex items-start gap-2 rounded-md border px-3 py-2 text-sm',
        severityClasses[props.kind],
        props.class,
      )
    "
    role="alert"
    aria-live="polite"
  >
    <component :is="severityIcons[props.kind]" class="mt-0.5 h-4 w-4 shrink-0" />
    <span class="flex-1"><slot /></span>
  </div>
</template>
