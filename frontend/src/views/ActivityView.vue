<script setup lang="ts">
import { onMounted, ref } from "vue";
import { auditApi } from "@/api";
import { ApiError } from "@/api/client";
import type { AuditEvent } from "@/api/types";
import { useToasts } from "@/composables/useToasts";
import AuditLogTable from "@/components/AuditLogTable.vue";
import { Button, Skeleton } from "@/components/ui";

const toast = useToasts();
const events = ref<AuditEvent[]>([]);
const total = ref(0);
const offset = ref(0);
const loading = ref(true);
const limit = 50;

async function load(): Promise<void> {
  loading.value = true;
  try {
    const page = await auditApi.mine({ limit, offset: offset.value });
    events.value = page.items;
    total.value = page.total;
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to load activity");
  } finally {
    loading.value = false;
  }
}

function next(): void {
  if (offset.value + limit < total.value) {
    offset.value += limit;
    load();
  }
}

function prev(): void {
  if (offset.value > 0) {
    offset.value = Math.max(0, offset.value - limit);
    load();
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-2xl font-bold">Share activity</h1>
      <p class="text-muted-foreground">
        Access and downloads of the packages you have shared
      </p>
    </div>

    <div v-if="loading" class="space-y-2">
      <Skeleton v-for="n in 6" :key="n" class="h-10 w-full" />
    </div>
    <template v-else>
      <AuditLogTable :events="events" />
      <div class="flex items-center justify-between text-sm text-muted-foreground">
        <span>{{ total }} event(s)</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="offset === 0" @click="prev">
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="offset + limit >= total"
            @click="next"
          >
            Next
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
