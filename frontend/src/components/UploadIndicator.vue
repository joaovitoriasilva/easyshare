<script setup lang="ts">
import { RouterLink } from "vue-router";
import { Loader2 } from "lucide-vue-next";
import { useUploads } from "@/composables/useUploads";

// Reads the shared, module-level upload state so a running upload stays visible
// no matter which view is mounted (or if none is).
const { activeBatches, hasActiveUploads } = useUploads();
</script>

<template>
  <div
    v-if="hasActiveUploads"
    class="fixed bottom-4 right-4 z-[250] w-72 max-w-[calc(100vw-2rem)] space-y-2"
    aria-live="polite"
  >
    <div
      v-for="batch in activeBatches"
      :key="batch.packageId"
      class="rounded-lg border bg-card p-3 shadow-lg"
    >
      <div class="flex items-center gap-2">
        <Loader2 class="h-4 w-4 shrink-0 animate-spin text-primary" />
        <RouterLink
          :to="{ name: 'package', params: { id: batch.packageId } }"
          class="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
        >
          {{ batch.name }}
        </RouterLink>
        <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
          {{ batch.percent }}%
        </span>
      </div>
      <div
        class="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        :aria-valuenow="batch.percent"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="`Uploading to ${batch.name}`"
      >
        <div
          class="h-full rounded-full bg-primary transition-[width] duration-200 ease-out"
          :style="{ width: `${batch.percent}%` }"
        />
      </div>
      <p class="mt-1.5 text-xs text-muted-foreground">
        {{ batch.done }} of {{ batch.total }} uploaded
        <template v-if="batch.failed > 0"> &middot; {{ batch.failed }} failed</template>
      </p>
    </div>
  </div>
</template>
