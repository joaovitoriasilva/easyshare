<script setup lang="ts">
import { computed } from "vue";
import { useNavigationProgress } from "@/composables/useNavigationProgress";

const { active, progress } = useNavigationProgress();

const barStyle = computed(() => ({
  width: `${Math.round(progress.value * 100)}%`,
}));
</script>

<template>
  <div
    class="pointer-events-none fixed inset-x-0 top-0 z-[200] h-0.5"
    aria-hidden="true"
  >
    <div
      v-show="active"
      class="h-full bg-primary transition-[width] duration-200 ease-out"
      :style="barStyle"
    />
  </div>
</template>
