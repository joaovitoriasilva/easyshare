<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Download, Lock, Package2 } from "lucide-vue-next";
import { publicApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PublicShare } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { isValidEmail } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Input,
  Label,
  Skeleton,
  Tooltip,
} from "@/components/ui";

const route = useRoute();
const token = String(route.params.token);
const toast = useToasts();

const share = ref<PublicShare | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const email = ref("");
const unlocked = ref(false);
const selected = ref<Set<number>>(new Set());

const emailValid = computed(() => isValidEmail(email.value));
const showEmailError = computed(() => email.value.length > 0 && !emailValid.value);

const files = computed(() => share.value?.files ?? []);
const allSelected = computed(
  () => files.value.length > 0 && selected.value.size === files.value.length,
);
const hasSelection = computed(() => selected.value.size > 0);
// Opaque, short-lived token returned by /access for restricted shares; used in
// place of the recipient's email so the email never appears in a download URL.
const downloadToken = ref<string | null>(null);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    share.value = await publicApi.view(token);
    unlocked.value = !share.value.requires_email;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Share not found";
  } finally {
    loading.value = false;
  }
}

async function unlock(): Promise<void> {
  error.value = null;
  try {
    share.value = await publicApi.access(token, email.value);
    downloadToken.value = share.value.download_token ?? null;
    unlocked.value = true;
    toast.success("Access granted");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Access denied";
  }
}

function toggle(id: number): void {
  const next = new Set(selected.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  selected.value = next;
}

function toggleAll(): void {
  selected.value = allSelected.value
    ? new Set()
    : new Set(files.value.map((file) => file.id));
}

function downloadFile(id: number, filename: string): void {
  downloadUrl(publicApi.fileUrl(token, id, downloadToken.value), filename);
  toast.success("Download started");
}

function downloadSelected(): void {
  const ids = hasSelection.value ? Array.from(selected.value) : [];
  downloadUrl(
    publicApi.downloadUrl(token, ids, downloadToken.value),
    `${share.value?.package_name ?? "package"}.zip`,
  );
  toast.info("Preparing your download\u2026");
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <Card v-if="loading">
      <CardHeader class="space-y-2">
        <Skeleton class="h-6 w-1/2" />
        <Skeleton class="h-4 w-3/4" />
      </CardHeader>
      <CardContent class="space-y-3">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
      </CardContent>
    </Card>

    <Card v-else-if="error && !share">
      <CardHeader>
        <CardTitle>Share unavailable</CardTitle>
        <CardDescription>{{ error }}</CardDescription>
      </CardHeader>
    </Card>

    <template v-else-if="share">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Package2 class="h-5 w-5 text-primary" />
            {{ share.package_name }}
          </CardTitle>
          <CardDescription v-if="share.package_description">
            {{ share.package_description }}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <div v-if="!unlocked" class="space-y-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Lock class="h-4 w-4" />
              This share is restricted. Enter an authorised email to continue.
            </div>
            <form class="space-y-3" @submit.prevent="unlock">
              <div class="space-y-2">
                <Label for="email">Email</Label>
                <Tooltip content="Enter a valid email address" :open="showEmailError">
                  <Input id="email" v-model="email" type="email" placeholder="you@example.com" />
                </Tooltip>
              </div>
              <Alert v-if="error" kind="error">{{ error }}</Alert>
              <Button type="submit" :disabled="!emailValid">Unlock</Button>
            </form>
          </div>

          <div v-else class="space-y-4">
            <div class="flex items-center justify-between gap-3">
              <label class="flex items-center gap-2 text-sm">
                <Checkbox :model-value="allSelected" @update:model-value="toggleAll" />
                Select all
              </label>
              <Button size="sm" class="shrink-0" @click="downloadSelected">
                <Download class="h-4 w-4" />
                {{ hasSelection ? `Download ${selected.size} selected` : "Download all" }}
              </Button>
            </div>

            <ul class="divide-y rounded-md border">
              <li
                v-for="file in files"
                :key="file.id"
                class="flex items-center justify-between gap-3 p-3"
              >
                <label class="flex min-w-0 items-center gap-3">
                  <Checkbox
                    :model-value="selected.has(file.id)"
                    @update:model-value="() => toggle(file.id)"
                  />
                  <span class="min-w-0">
                    <span class="block truncate text-sm font-medium">{{ file.filename }}</span>
                    <span class="block text-xs text-muted-foreground">
                      {{ formatBytes(file.size) }}
                    </span>
                  </span>
                </label>
                <Button
                  variant="ghost"
                  size="icon"
                  class="shrink-0"
                  aria-label="Download file"
                  @click="downloadFile(file.id, file.filename)"
                >
                  <Download class="h-4 w-4" />
                </Button>
              </li>
            </ul>
            <p v-if="files.length === 0" class="text-sm text-muted-foreground">
              This package has no files.
            </p>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
