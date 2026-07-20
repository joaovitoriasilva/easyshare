<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Calendar, Download, Pencil, RotateCw, Trash2, Upload, X } from "lucide-vue-next";
import { packagesApi, sharesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { Package, PackageStats, Share, Visibility } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { copyText } from "@/lib/clipboard";
import { fileIcon } from "@/lib/fileIcon";
import { invalidEmails, parseEmailList } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import { useConfirm } from "@/composables/useConfirm";
import { useUploads, type UploadItem } from "@/composables/useUploads";
import { useAuthStore } from "@/stores/auth";
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
  QrCode,
  Skeleton,
  Tooltip,
} from "@/components/ui";

const route = useRoute();
const router = useRouter();
const toast = useToasts();
const { confirm } = useConfirm();
const auth = useAuthStore();
const packageId = Number(route.params.id);

const pkg = ref<Package | null>(null);
const share = ref<Share | null>(null);
const stats = ref<PackageStats | null>(null);
const error = ref<string | null>(null);
const loading = ref(true);
const downloadingAll = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);

// Upload state lives in a module-level composable, keyed by package id, so a
// running upload's progress is preserved when the user leaves this package and
// comes back to it.
const { uploadsFor, isUploading, startUploads, cancelUpload, retryUpload, dismissUpload } =
  useUploads();
const uploads = uploadsFor(packageId);
const uploading = isUploading(packageId);

const editing = ref(false);
const editName = ref("");
const editDescription = ref("");
const savingDetails = ref(false);

const visibility = ref<Visibility>("public");
const emailsText = ref("");
const expiresAt = ref(""); // <input type="datetime-local"> value (local time)

// File list controls: filter text, sort key and multi-select for bulk actions.
const fileFilter = ref("");
const fileSort = ref<"name" | "size" | "date">("name");
const selectedFiles = ref<Set<number>>(new Set());

const shareLink = computed(() =>
  share.value ? `${window.location.origin}/s/${share.value.token}` : "",
);

const displayedFiles = computed(() => {
  const files = pkg.value?.files ?? [];
  const term = fileFilter.value.trim().toLowerCase();
  const filtered = term
    ? files.filter((file) => file.filename.toLowerCase().includes(term))
    : files.slice();
  filtered.sort((a, b) => {
    if (fileSort.value === "size") {
      return b.size - a.size;
    }
    if (fileSort.value === "date") {
      return b.created_at.localeCompare(a.created_at);
    }
    return a.filename.localeCompare(b.filename);
  });
  return filtered;
});

const allFilesSelected = computed(
  () =>
    displayedFiles.value.length > 0 &&
    displayedFiles.value.every((file) => selectedFiles.value.has(file.id)),
);
const hasFileSelection = computed(() => selectedFiles.value.size > 0);

const shareExpired = computed(() => {
  const iso = share.value?.expires_at;
  return iso != null && new Date(iso).getTime() <= Date.now();
});

const lastDownloaded = computed(() => {
  const iso = stats.value?.last_downloaded_at;
  return iso ? new Date(iso).toLocaleString() : null;
});

const expiryLabel = computed(() => {
  const iso = share.value?.expires_at;
  return iso ? new Date(iso).toLocaleString() : null;
});

// Warn owners that, without email verification configured, a restricted share
// admits anyone who knows an allow-listed address (no proof of ownership).
const showUnverifiedRestrictedWarning = computed(
  () => visibility.value === "restricted" && !auth.emailVerificationEnabled,
);

function toggleFile(id: number): void {
  const next = new Set(selectedFiles.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  selectedFiles.value = next;
}

function toggleAllFiles(): void {
  selectedFiles.value = allFilesSelected.value
    ? new Set()
    : new Set(displayedFiles.value.map((file) => file.id));
}

/** ISO string for the datetime-local value, or null when the field is empty. */
function expiryPayload(): string | null {
  return expiresAt.value ? new Date(expiresAt.value).toISOString() : null;
}

/** Convert an ISO timestamp into the local value a datetime-local input wants. */
function toDatetimeLocal(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (value: number): string => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    pkg.value = await packagesApi.get(packageId);
    try {
      share.value = await sharesApi.get(packageId);
      visibility.value = share.value.visibility;
      emailsText.value = share.value.allowed_emails.join(", ");
      expiresAt.value = toDatetimeLocal(share.value.expires_at);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        share.value = null;
      } else {
        throw err;
      }
    }
    packagesApi.stats(packageId).then((value) => {
      stats.value = value;
    }).catch(() => {
      stats.value = null;
    });
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load package";
  } finally {
    loading.value = false;
  }
}

function fileDownloads(fileId: number): number {
  return stats.value?.file_downloads[fileId] ?? 0;
}

function uploadStatusLabel(item: UploadItem): string {
  if (item.status === "error") {
    return "Failed";
  }
  if (item.status === "canceled") {
    return "Canceled";
  }
  return `${Math.round(item.progress * 100)}%`;
}

const emailIssues = computed(() => invalidEmails(emailsText.value));
const restrictedEmailsOk = computed(
  () =>
    visibility.value !== "restricted" ||
    (parseEmailList(emailsText.value).length > 0 && emailIssues.value.length === 0),
);

function startEdit(): void {
  if (!pkg.value) {
    return;
  }
  editName.value = pkg.value.name;
  editDescription.value = pkg.value.description ?? "";
  editing.value = true;
}

function cancelEdit(): void {
  editing.value = false;
}

async function saveDetails(): Promise<void> {
  if (!editName.value.trim()) {
    toast.warning("Package name is required");
    return;
  }
  savingDetails.value = true;
  try {
    pkg.value = await packagesApi.update(packageId, {
      name: editName.value.trim(),
      description: editDescription.value.trim() || null,
    });
    editing.value = false;
    toast.success("Package updated");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update package");
  } finally {
    savingDetails.value = false;
  }
}

function runUploads(files: File[]): void {
  void startUploads(packageId, files, auth.maxFileSize);
}

function onUpload(event: Event): void {
  const target = event.target as HTMLInputElement;
  const files = target.files ? Array.from(target.files) : [];
  runUploads(files);
  target.value = "";
}

function onDrop(event: DragEvent): void {
  dragging.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    runUploads(Array.from(files));
  }
}

// Refresh the file list once an upload batch finishes. A watcher (rather than
// awaiting the upload) means the view still updates even if it was unmounted
// while the upload ran and then remounted before it completed.
watch(uploading, (active, wasActive) => {
  if (wasActive && !active) {
    packagesApi
      .get(packageId)
      .then((value) => {
        pkg.value = value;
      })
      .catch(() => {
        /* a subsequent load() will surface any real error */
      });
  }
});

async function removeFile(fileId: number): Promise<void> {
  const confirmed = await confirm({
    title: "Remove file",
    message: "This file will be permanently deleted from the package.",
    confirmText: "Remove",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  const current = pkg.value;
  if (!current) {
    return;
  }
  // Optimistically drop the file; restore the list if the request fails.
  const previous = current.files;
  current.files = previous.filter((file) => file.id !== fileId);
  if (selectedFiles.value.has(fileId)) {
    const nextSelected = new Set(selectedFiles.value);
    nextSelected.delete(fileId);
    selectedFiles.value = nextSelected;
  }
  try {
    await packagesApi.removeFile(packageId, fileId);
    toast.success("File removed");
  } catch (err) {
    current.files = previous;
    toast.error(err instanceof ApiError ? err.message : "Failed to remove file");
  }
}

async function removeAllFiles(): Promise<void> {
  if (!pkg.value?.files.length) {
    return;
  }
  const confirmed = await confirm({
    title: "Delete all files",
    message: "Every file in this package will be permanently deleted.",
    confirmText: "Delete all",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  const current = pkg.value;
  if (!current) {
    return;
  }
  // Optimistically clear the list; restore it if the request fails.
  const previous = current.files;
  current.files = [];
  selectedFiles.value = new Set();
  try {
    await packagesApi.removeAllFiles(packageId);
    toast.success("All files removed");
  } catch (err) {
    current.files = previous;
    toast.error(err instanceof ApiError ? err.message : "Failed to remove files");
  }
}

async function deleteSelectedFiles(): Promise<void> {
  const ids = Array.from(selectedFiles.value);
  if (ids.length === 0) {
    return;
  }
  const confirmed = await confirm({
    title: "Delete selected files",
    message: `${ids.length} file(s) will be permanently deleted.`,
    confirmText: "Delete",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  const current = pkg.value;
  if (!current) {
    return;
  }
  // Optimistically drop the selected files; restore them if the request fails.
  const idSet = new Set(ids);
  const previous = current.files;
  current.files = previous.filter((file) => !idSet.has(file.id));
  selectedFiles.value = new Set();
  try {
    await packagesApi.removeAllFiles(packageId, ids);
    toast.success("Files removed");
  } catch (err) {
    current.files = previous;
    toast.error(err instanceof ApiError ? err.message : "Failed to remove files");
  }
}

async function triggerDownload(
  buildUrl: (token: string) => string,
  filename: string,
  failMessage: string,
): Promise<void> {
  try {
    const { token } = await packagesApi.downloadToken(packageId);
    downloadUrl(buildUrl(token), filename);
  } catch {
    toast.error(failMessage);
  }
}

function downloadOwned(fileId: number, filename: string): void {
  void triggerDownload(
    (token) => packagesApi.fileDownloadUrl(packageId, fileId, token),
    filename,
    "Failed to download file",
  );
}

async function downloadAllOwned(): Promise<void> {
  if (!pkg.value?.files.length) {
    return;
  }
  const name = pkg.value.name;
  downloadingAll.value = true;
  await triggerDownload(
    (token) => packagesApi.downloadAllUrl(packageId, token),
    `${name}.zip`,
    "Failed to download files",
  );
  downloadingAll.value = false;
}

function downloadSelectedOwned(): void {
  const ids = Array.from(selectedFiles.value);
  if (ids.length === 0) {
    return;
  }
  const name = pkg.value?.name ?? "package";
  void triggerDownload(
    (token) => packagesApi.downloadAllUrl(packageId, token, ids),
    `${name}.zip`,
    "Failed to download files",
  );
}

async function enableSharing(): Promise<void> {
  try {
    share.value = await sharesApi.enable(
      packageId,
      visibility.value,
      parseEmailList(emailsText.value),
      expiryPayload(),
    );
    toast.success("Sharing enabled");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to enable sharing");
  }
}

async function updateSharing(): Promise<void> {
  try {
    share.value = await sharesApi.update(packageId, {
      visibility: visibility.value,
      allowed_emails: parseEmailList(emailsText.value),
      expires_at: expiryPayload(),
    });
    toast.success("Changes saved");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update sharing");
  }
}

async function toggleEnabled(): Promise<void> {
  if (!share.value) {
    return;
  }
  const next = !share.value.is_enabled;
  try {
    share.value = await sharesApi.update(packageId, { is_enabled: next });
    toast.success(next ? "Sharing resumed" : "Sharing paused");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update sharing");
  }
}

async function disableSharing(): Promise<void> {
  const confirmed = await confirm({
    title: "Disable sharing",
    message: "The share link will stop working for everyone who has it.",
    confirmText: "Disable",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  try {
    await sharesApi.disable(packageId);
    share.value = null;
    toast.success("Sharing disabled");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to disable sharing");
  }
}

async function deletePackage(): Promise<void> {
  const confirmed = await confirm({
    title: "Delete package",
    message: `"${pkg.value?.name ?? "This package"}" and all its files will be permanently deleted.`,
    confirmText: "Delete",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  try {
    await packagesApi.remove(packageId);
    toast.success("Package deleted");
    router.push("/dashboard");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to delete package");
  }
}

async function copyLink(): Promise<void> {
  const copied = await copyText(shareLink.value);
  if (copied) {
    toast.success("Link copied to clipboard");
  } else {
    toast.error("Couldn't copy the link");
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <Button variant="ghost" size="sm" @click="router.push('/dashboard')">
      <ArrowLeft class="h-4 w-4" /> Back
    </Button>

    <Alert v-if="error" kind="error">{{ error }}</Alert>

    <div v-if="loading" class="space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div class="space-y-2">
          <Skeleton class="h-8 w-48" />
          <Skeleton class="h-4 w-64" />
        </div>
        <Skeleton class="h-9 w-40 shrink-0" />
      </div>
      <div class="grid gap-4 lg:grid-cols-2">
        <Skeleton class="h-56 w-full rounded-lg" />
        <Skeleton class="h-56 w-full rounded-lg" />
      </div>
    </div>

    <template v-else-if="pkg">
      <div v-if="!editing" class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0">
          <h1 class="break-words text-2xl font-bold">{{ pkg.name }}</h1>
          <p v-if="pkg.description" class="break-words text-muted-foreground">{{ pkg.description }}</p>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" @click="startEdit">
            <Pencil class="h-4 w-4" /> Edit
          </Button>
          <Button variant="destructive" size="sm" @click="deletePackage">
            <Trash2 class="h-4 w-4" /> Delete package
          </Button>
        </div>
      </div>

      <Card v-else>
        <CardHeader>
          <CardTitle>Edit package</CardTitle>
          <CardDescription>Update the package name and description.</CardDescription>
        </CardHeader>
        <form @submit.prevent="saveDetails">
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <Label for="edit-name">Name</Label>
              <Input id="edit-name" v-model="editName" placeholder="Project assets" />
            </div>
            <div class="space-y-2">
              <Label for="edit-desc">Description</Label>
              <Input id="edit-desc" v-model="editDescription" placeholder="Optional" />
            </div>
            <div class="flex gap-2">
              <Button type="submit" :disabled="savingDetails">
                {{ savingDetails ? "Saving..." : "Save" }}
              </Button>
              <Button type="button" variant="outline" @click="cancelEdit">Cancel</Button>
            </div>
          </CardContent>
        </form>
      </Card>

      <div class="grid gap-4 lg:grid-cols-2 lg:items-start">
        <Card>
          <CardHeader>
            <CardTitle>Files</CardTitle>
            <CardDescription>
              Upload one or more files to this package.
              <span v-if="stats">
                &middot; {{ stats.views }} view{{ stats.views === 1 ? "" : "s" }}
                &middot; {{ stats.downloads }} download{{ stats.downloads === 1 ? "" : "s" }}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <input
              ref="fileInput"
              type="file"
              multiple
              class="hidden"
              @change="onUpload"
            />

            <div
              role="button"
              tabindex="0"
              aria-label="Upload files"
              class="flex flex-col items-center justify-center rounded-md border border-dashed px-4 py-8 text-center transition-colors"
              :class="[
                dragging ? 'border-primary bg-primary/5' : 'border-input',
                uploading
                  ? 'pointer-events-none opacity-60'
                  : 'cursor-pointer hover:border-primary',
              ]"
              @click="fileInput?.click()"
              @keydown.enter.prevent="fileInput?.click()"
              @keydown.space.prevent="fileInput?.click()"
              @dragover.prevent="dragging = true"
              @dragenter.prevent="dragging = true"
              @dragleave.prevent="dragging = false"
              @drop.prevent="onDrop"
            >
              <div class="pointer-events-none flex flex-col items-center gap-1">
                <Upload class="h-6 w-6 text-muted-foreground" />
                <p class="text-sm">
                  <span class="font-medium text-primary">Click to upload</span>
                  or drag and drop
                </p>
                <p class="text-xs text-muted-foreground">
                  Up to {{ formatBytes(auth.maxFileSize) }} per file
                </p>
              </div>
            </div>

            <ul v-if="uploads.length" class="space-y-3">
              <li v-for="(item, index) in uploads" :key="item.id" class="space-y-1.5">
                <div class="flex items-center justify-between gap-2 text-xs">
                  <span class="min-w-0 truncate">{{ item.name }}</span>
                  <span
                    class="shrink-0"
                    :class="
                      item.status === 'error' || item.status === 'canceled'
                        ? 'text-destructive'
                        : 'text-muted-foreground'
                    "
                  >
                    {{ uploadStatusLabel(item) }}
                  </span>
                </div>
                <div
                  class="h-1.5 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  :aria-valuenow="Math.round(item.progress * 100)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-label="`Upload progress for ${item.name}`"
                >
                  <div
                    class="h-full rounded-full transition-all"
                    :class="
                      item.status === 'error' || item.status === 'canceled'
                        ? 'bg-destructive'
                        : 'bg-primary'
                    "
                    :style="{ width: `${Math.round(item.progress * 100)}%` }"
                  />
                </div>
                <div v-if="item.status === 'uploading'">
                  <Button
                    variant="ghost"
                    size="sm"
                    class="h-8 gap-1.5 px-2.5 text-xs text-muted-foreground"
                    @click="cancelUpload(packageId, index)"
                  >
                    <X class="h-4 w-4" /> Cancel
                  </Button>
                </div>
                <div
                  v-else-if="item.status === 'error' || item.status === 'canceled'"
                  class="flex flex-wrap gap-2"
                >
                  <Button
                    variant="outline"
                    size="sm"
                    class="h-8 gap-1.5 px-2.5 text-xs"
                    @click="retryUpload(packageId, index)"
                  >
                    <RotateCw class="h-4 w-4" /> Retry
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="h-8 gap-1.5 px-2.5 text-xs text-muted-foreground"
                    @click="dismissUpload(packageId, index)"
                  >
                    <X class="h-4 w-4" /> Dismiss
                  </Button>
                </div>
              </li>
            </ul>

            <div v-if="pkg.files.length" class="space-y-3">
              <div class="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  :disabled="downloadingAll"
                  @click="downloadAllOwned"
                >
                  <Download class="h-4 w-4" />
                  {{ downloadingAll ? "Preparing..." : "Download all" }}
                </Button>
                <Button variant="destructive" @click="removeAllFiles">
                  <Trash2 class="h-4 w-4" /> Delete all
                </Button>
                <template v-if="hasFileSelection">
                  <Button variant="secondary" @click="downloadSelectedOwned">
                    <Download class="h-4 w-4" /> Download {{ selectedFiles.size }} selected
                  </Button>
                  <Button variant="destructive" @click="deleteSelectedFiles">
                    <Trash2 class="h-4 w-4" /> Delete {{ selectedFiles.size }} selected
                  </Button>
                </template>
              </div>

              <div class="flex flex-col gap-2 sm:flex-row">
                <Input
                  v-model="fileFilter"
                  placeholder="Filter files..."
                  class="sm:max-w-xs"
                />
                <select
                  v-model="fileSort"
                  aria-label="Sort files"
                  class="h-10 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="name">Name (A–Z)</option>
                  <option value="size">Size (largest)</option>
                  <option value="date">Newest first</option>
                </select>
              </div>

              <label
                v-if="displayedFiles.length"
                class="flex items-center gap-2 px-1 text-xs text-muted-foreground"
              >
                <Checkbox
                  :model-value="allFilesSelected"
                  @update:model-value="toggleAllFiles"
                />
                Select all
              </label>
            </div>

            <ul v-if="displayedFiles.length" class="divide-y rounded-md border">
              <li
                v-for="file in displayedFiles"
                :key="file.id"
                class="flex items-center justify-between gap-3 p-3"
              >
                <label class="flex min-w-0 items-center gap-3">
                  <Checkbox
                    :model-value="selectedFiles.has(file.id)"
                    @update:model-value="() => toggleFile(file.id)"
                  />
                  <component
                    :is="fileIcon(file.filename)"
                    class="h-4 w-4 shrink-0 text-muted-foreground"
                  />
                  <span class="min-w-0">
                    <span class="block truncate text-sm font-medium">{{ file.filename }}</span>
                    <span class="block text-xs text-muted-foreground">
                      {{ formatBytes(file.size) }}
                      <span v-if="stats">
                        &middot; {{ fileDownloads(file.id) }} download{{
                          fileDownloads(file.id) === 1 ? "" : "s"
                        }}
                      </span>
                    </span>
                  </span>
                </label>
                <div class="flex shrink-0 gap-1">
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
            <p v-else-if="pkg.files.length" class="text-sm text-muted-foreground">
              No files match “{{ fileFilter.trim() }}”.
            </p>
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
              <Tooltip
                :content="'Invalid email(s): ' + emailIssues.join(', ')"
                :open="emailIssues.length > 0"
              >
                <Input
                  id="emails"
                  v-model="emailsText"
                  placeholder="alice@example.com, bob@example.com"
                />
              </Tooltip>
              <p class="text-xs text-muted-foreground">
                Separate multiple emails with commas.
              </p>
            </div>

            <Alert v-if="showUnverifiedRestrictedWarning" kind="warning">
              Email verification is not configured, so anyone who knows an
              allowed address can open this share. Configure SMTP on the server
              to require a one-time code sent to the recipient.
            </Alert>

            <div class="space-y-2">
              <Label for="expires">Expiry (optional)</Label>
              <div class="flex flex-wrap items-center gap-2">
                <Input
                  id="expires"
                  v-model="expiresAt"
                  type="datetime-local"
                  class="min-w-0 sm:max-w-xs"
                />
                <Button
                  v-if="expiresAt"
                  variant="ghost"
                  size="sm"
                  @click="expiresAt = ''"
                >
                  Clear
                </Button>
              </div>
              <p class="text-xs text-muted-foreground">
                Leave empty for a link that never expires.
              </p>
            </div>

            <div v-if="!share" class="flex">
              <Button :disabled="!restrictedEmailsOk" @click="enableSharing">Enable sharing</Button>
            </div>

            <div v-else class="space-y-4">
              <div class="space-y-2">
                <Label for="link">Share link</Label>
                <div class="flex gap-2">
                  <Input id="link" :model-value="shareLink" class="min-w-0" readonly />
                  <Button variant="secondary" @click="copyLink">
                    Copy
                  </Button>
                </div>
                <div class="flex items-center gap-3 pt-1">
                  <QrCode :value="shareLink" label="QR code for the share link" />
                  <p class="text-xs text-muted-foreground">
                    Scan this code to open the share link on a phone or another
                    device.
                  </p>
                </div>
                <p class="text-xs" :class="share.is_enabled ? 'text-green-600' : 'text-muted-foreground'">
                  {{ share.is_enabled ? "Sharing is active" : "Sharing is paused" }}
                </p>
                <p
                  v-if="expiryLabel"
                  class="flex items-center gap-1 text-xs"
                  :class="shareExpired ? 'text-destructive' : 'text-muted-foreground'"
                >
                  <Calendar class="h-3 w-3" />
                  {{ shareExpired ? `Expired ${expiryLabel}` : `Expires ${expiryLabel}` }}
                </p>
                <p v-if="lastDownloaded" class="text-xs text-muted-foreground">
                  Last downloaded {{ lastDownloaded }}
                </p>
              </div>
              <div class="flex flex-wrap gap-2">
                <Button variant="secondary" :disabled="!restrictedEmailsOk" @click="updateSharing">Save changes</Button>
                <Button variant="outline" @click="toggleEnabled">
                  {{ share.is_enabled ? "Pause" : "Resume" }}
                </Button>
                <Button variant="destructive" @click="disableSharing">Disable sharing</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>

