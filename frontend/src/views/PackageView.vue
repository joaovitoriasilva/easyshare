<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Download, Trash2, Upload } from "lucide-vue-next";
import { packagesApi, sharesApi } from "@/api";
import { ApiError, getToken } from "@/api/client";
import type { Package, Share, Visibility } from "@/api/types";
import { formatBytes } from "@/lib/format";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@/components/ui";

const route = useRoute();
const router = useRouter();
const packageId = Number(route.params.id);

const pkg = ref<Package | null>(null);
const share = ref<Share | null>(null);
const error = ref<string | null>(null);
const loading = ref(true);
const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const visibility = ref<Visibility>("public");
const emailsText = ref("");

const shareLink = computed(() =>
  share.value ? `${window.location.origin}/s/${share.value.token}` : "",
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    pkg.value = await packagesApi.get(packageId);
    try {
      share.value = await sharesApi.get(packageId);
      visibility.value = share.value.visibility;
      emailsText.value = share.value.allowed_emails.join(", ");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        share.value = null;
      } else {
        throw err;
      }
    }
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load package";
  } finally {
    loading.value = false;
  }
}

function parseEmails(): string[] {
  return emailsText.value
    .split(/[\s,]+/)
    .map((email) => email.trim())
    .filter(Boolean);
}

async function onUpload(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (!files || files.length === 0) {
    return;
  }
  uploading.value = true;
  error.value = null;
  try {
    for (const file of Array.from(files)) {
      await packagesApi.uploadFile(packageId, file);
    }
    pkg.value = await packagesApi.get(packageId);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Upload failed";
  } finally {
    uploading.value = false;
    if (fileInput.value) {
      fileInput.value.value = "";
    }
  }
}

async function removeFile(fileId: number): Promise<void> {
  await packagesApi.removeFile(packageId, fileId);
  pkg.value = await packagesApi.get(packageId);
}

function downloadOwned(fileId: number, filename: string): void {
  const token = getToken();
  fetch(`/api/packages/${packageId}/files/${fileId}/download`, {
    headers: token ? { Authorization: "Bearer " + token } : {},
  })
    .then((response) => response.blob())
    .then((blob) => triggerDownload(URL.createObjectURL(blob), filename));
}

function triggerDownload(url: string, filename: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
}

async function enableSharing(): Promise<void> {
  error.value = null;
  try {
    share.value = await sharesApi.enable(packageId, visibility.value, parseEmails());
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to enable sharing";
  }
}

async function updateSharing(): Promise<void> {
  error.value = null;
  try {
    share.value = await sharesApi.update(packageId, {
      visibility: visibility.value,
      allowed_emails: parseEmails(),
    });
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to update sharing";
  }
}

async function toggleEnabled(): Promise<void> {
  if (!share.value) {
    return;
  }
  share.value = await sharesApi.update(packageId, {
    is_enabled: !share.value.is_enabled,
  });
}

async function disableSharing(): Promise<void> {
  await sharesApi.disable(packageId);
  share.value = null;
}

async function deletePackage(): Promise<void> {
  await packagesApi.remove(packageId);
  router.push("/dashboard");
}

function copyLink(): void {
  navigator.clipboard.writeText(shareLink.value);
}

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <Button variant="ghost" size="sm" @click="router.push('/dashboard')">
      <ArrowLeft class="h-4 w-4" /> Back
    </Button>

    <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="loading" class="text-muted-foreground">Loading...</p>

    <template v-else-if="pkg">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-2xl font-bold">{{ pkg.name }}</h1>
          <p v-if="pkg.description" class="text-muted-foreground">{{ pkg.description }}</p>
        </div>
        <Button variant="destructive" size="sm" @click="deletePackage">
          <Trash2 class="h-4 w-4" /> Delete package
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Files</CardTitle>
          <CardDescription>Upload one or more files to this package.</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <input
            ref="fileInput"
            type="file"
            multiple
            class="hidden"
            @change="onUpload"
          />
          <Button :disabled="uploading" @click="fileInput?.click()">
            <Upload class="h-4 w-4" />
            {{ uploading ? "Uploading..." : "Upload files" }}
          </Button>

          <ul v-if="pkg.files.length" class="divide-y rounded-md border">
            <li
              v-for="file in pkg.files"
              :key="file.id"
              class="flex items-center justify-between p-3"
            >
              <div>
                <p class="text-sm font-medium">{{ file.filename }}</p>
                <p class="text-xs text-muted-foreground">{{ formatBytes(file.size) }}</p>
              </div>
              <div class="flex gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Download"
                  @click="downloadOwned(file.id, file.filename)"
                >
                  <Download class="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Delete file"
                  @click="removeFile(file.id)"
                >
                  <Trash2 class="h-4 w-4" />
                </Button>
              </div>
            </li>
          </ul>
          <p v-else class="text-sm text-muted-foreground">No files yet.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sharing</CardTitle>
          <CardDescription>
            Sharing is off by default. Enable it to generate a secure link.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label>Visibility</Label>
            <div class="flex gap-4">
              <label class="flex items-center gap-2 text-sm">
                <input v-model="visibility" type="radio" value="public" /> Public
              </label>
              <label class="flex items-center gap-2 text-sm">
                <input v-model="visibility" type="radio" value="restricted" />
                Restricted (by email)
              </label>
            </div>
          </div>

          <div v-if="visibility === 'restricted'" class="space-y-2">
            <Label for="emails">Allowed emails</Label>
            <Input
              id="emails"
              v-model="emailsText"
              placeholder="alice@example.com, bob@example.com"
            />
            <p class="text-xs text-muted-foreground">
              Separate multiple emails with commas.
            </p>
          </div>

          <div v-if="!share" class="flex">
            <Button @click="enableSharing">Enable sharing</Button>
          </div>

          <div v-else class="space-y-4">
            <div class="space-y-2">
              <Label for="link">Share link</Label>
              <div class="flex gap-2">
                <Input id="link" :model-value="shareLink" readonly />
                <Button variant="secondary" @click="copyLink">
                  Copy
                </Button>
              </div>
              <p class="text-xs" :class="share.is_enabled ? 'text-green-600' : 'text-muted-foreground'">
                {{ share.is_enabled ? "Sharing is active" : "Sharing is paused" }}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button variant="secondary" @click="updateSharing">Save changes</Button>
              <Button variant="outline" @click="toggleEnabled">
                {{ share.is_enabled ? "Pause" : "Resume" }}
              </Button>
              <Button variant="destructive" @click="disableSharing">Disable sharing</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
