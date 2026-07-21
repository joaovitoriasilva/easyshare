<script setup lang="ts">
import { computed } from "vue";
import { estimatePasswordStrength } from "@/lib/passwordStrength";

const props = defineProps<{ password: string }>();

const strength = computed(() => estimatePasswordStrength(props.password));

// Colour ramp from weak (red) to strong (green), matching the app's severity
// palette (see lib/severity.ts).
const barClasses = ["", "bg-red-500", "bg-amber-500", "bg-green-500", "bg-green-500"];
const activeBar = computed(() => barClasses[strength.value.score]);
</script>

<template>
  <div v-if="password" class="space-y-1">
    <div class="flex gap-1" aria-hidden="true">
      <span
        v-for="segment in 4"
        :key="segment"
        class="h-1 flex-1 rounded-full transition-colors"
        :class="segment <= strength.score ? activeBar : 'bg-muted'"
      />
    </div>
    <p class="text-xs text-muted-foreground" aria-live="polite">
      Password strength: <span class="font-medium">{{ strength.label }}</span>
    </p>
  </div>
</template>
