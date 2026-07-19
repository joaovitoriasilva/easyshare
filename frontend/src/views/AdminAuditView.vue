<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { auditApi } from "@/api";
import { ApiError } from "@/api/client";
import type { AuditEvent } from "@/api/types";
import { useToasts } from "@/composables/useToasts";
import AuditLogTable from "@/components/AuditLogTable.vue";
import { Button, Input, Label, Skeleton } from "@/components/ui";

const toast = useToasts();
const events = ref<AuditEvent[]>([]);
const total = ref(0);
const offset = ref(0);
const loading = ref(true);
const action = ref("");
const actor = ref("");
const limit = 50;
const retention = ref<number | null>(null);

const retentionLabel = computed(() => {
  if (retention.value === null) {
    return "";
  }
  return retention.value > 0
    ? `Events older than ${retention.value} day${retention.value === 1 ? "" : "s"} are automatically deleted.`
    : "Events are kept indefinitely.";
});

async function load(): Promise<void> {
  loading.value = true;
  try {
    const page = await auditApi.all({
      limit,
      offset: offset.value,
      action: action.value || undefined,
      actor: actor.value || undefined,
    });
    events.value = page.items;
    total.value = page.total;
    retention.value = page.retention_days;
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to load audit log");
  } finally {
    loading.value = false;
  }
}

function applyFilters(): void {
  offset.value = 0;
  load();
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
      <h1 class="text-2xl font-bold">Audit log</h1>
      <p class="text-muted-foreground">All security events across the instance</p>
      <p v-if="retention !== null" class="mt-1 text-sm text-muted-foreground">
        {{ retentionLabel }}
      </p>
    </div>

    <form class="flex flex-wrap items-end gap-3" @submit.prevent="applyFilters">
      <div class="space-y-1">
        <Label for="filter-action">Action</Label>
        <Input id="filter-action" v-model="action" placeholder="e.g. share.download" />
      </div>
      <div class="space-y-1">
        <Label for="filter-actor">Actor</Label>
        <Input id="filter-actor" v-model="actor" placeholder="e.g. user:1 or an email" />
      </div>
      <Button type="submit" variant="outline" size="sm">Filter</Button>
    </form>

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
