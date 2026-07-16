<script setup lang="ts">
import type { AuditEvent } from "@/api/types";

defineProps<{ events: AuditEvent[] }>();

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function formatDetail(detail: Record<string, unknown> | null): string {
  if (!detail) {
    return "";
  }
  return Object.entries(detail)
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");
}
</script>

<template>
  <div class="overflow-x-auto rounded-md border">
    <table class="w-full text-sm">
      <thead class="bg-muted/50 text-left text-muted-foreground">
        <tr>
          <th class="p-3 font-medium">Time</th>
          <th class="p-3 font-medium">Action</th>
          <th class="p-3 font-medium">Actor</th>
          <th class="p-3 font-medium">Target</th>
          <th class="p-3 font-medium">IP</th>
          <th class="p-3 font-medium">Detail</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="event in events" :key="event.id" class="border-t">
          <td class="whitespace-nowrap p-3 text-muted-foreground">
            {{ formatTime(event.created_at) }}
          </td>
          <td class="p-3">
            <code class="rounded bg-muted px-1.5 py-0.5 text-xs">{{ event.action }}</code>
          </td>
          <td class="p-3">{{ event.actor ?? "—" }}</td>
          <td class="p-3 text-muted-foreground">{{ event.target ?? "—" }}</td>
          <td class="p-3 text-muted-foreground">{{ event.client_ip ?? "—" }}</td>
          <td class="p-3 text-muted-foreground">{{ formatDetail(event.detail) }}</td>
        </tr>
        <tr v-if="events.length === 0">
          <td colspan="6" class="p-6 text-center text-muted-foreground">
            No activity yet.
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
