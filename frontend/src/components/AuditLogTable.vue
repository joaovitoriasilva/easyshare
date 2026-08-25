<script setup lang="ts">
import type { AuditEvent } from "@/api/types";
import {
  formatAuditAction,
  formatAuditActor,
  formatAuditDetail,
  formatAuditTarget,
} from "@/lib/audit";

defineProps<{ events: AuditEvent[]; technical?: boolean }>();

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

</script>

<template>
  <div v-if="events.length === 0" class="rounded-md border p-4 text-center text-muted-foreground">
    No activity yet.
  </div>

  <ol v-else class="space-y-3 lg:hidden">
    <li v-for="event in events" :key="event.id" class="rounded-md border bg-card p-4">
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0">
          <p class="font-medium">{{ formatAuditAction(event.action) }}</p>
          <code
            v-if="technical"
            class="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
          >
            {{ event.action }}
          </code>
        </div>
        <time :datetime="event.created_at" class="shrink-0 text-right text-xs text-muted-foreground">
          {{ formatTime(event.created_at) }}
        </time>
      </div>
      <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">Actor</dt>
          <dd class="break-words">{{ formatAuditActor(event.actor) }}</dd>
        </div>
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">Target</dt>
          <dd class="break-words">{{ formatAuditTarget(event.target) }}</dd>
        </div>
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">IP address</dt>
          <dd class="break-words">{{ event.client_ip ?? "None" }}</dd>
        </div>
        <div v-if="formatAuditDetail(event.detail)" class="min-w-0">
          <dt class="text-xs text-muted-foreground">Details</dt>
          <dd class="break-words">{{ formatAuditDetail(event.detail) }}</dd>
        </div>
      </dl>
    </li>
  </ol>

  <div v-if="events.length > 0" class="hidden overflow-hidden rounded-md border lg:block">
    <table class="w-full table-fixed text-sm">
      <colgroup>
        <col class="w-[21%]" />
        <col class="w-[19%]" />
        <col class="w-[14%]" />
        <col class="w-[14%]" />
        <col class="w-[14%]" />
        <col class="w-[18%]" />
      </colgroup>
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
          <td class="break-words p-3">
            <span class="font-medium">{{ formatAuditAction(event.action) }}</span>
            <code
              v-if="technical"
              class="mt-1 block w-fit rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
            >
              {{ event.action }}
            </code>
          </td>
          <td class="break-words p-3">{{ formatAuditActor(event.actor) }}</td>
          <td class="break-words p-3 text-muted-foreground">
            {{ formatAuditTarget(event.target) }}
          </td>
          <td class="break-words p-3 text-muted-foreground">
            {{ event.client_ip ?? "None" }}
          </td>
          <td class="break-words p-3 text-muted-foreground">
            {{ formatAuditDetail(event.detail) || "None" }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
