<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Download, Pencil, Trash2, Upload } from "lucide-vue-next";
import { packagesApi, sharesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { Package, PackageStats, Share, Visibility } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { invalidEmails, parseEmailList } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import { useConfirm } from "@/composables/useConfirm";
import { useAuthStore } from "@/stores/auth";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
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
const uploading = ref(false);
const downloadingAll = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);

interface UploadItem {
  name: string;
  progress: number;
  status: "uploading" | "done" | "error";
}
const uploads = ref<UploadItem[]>([]);

const editing = ref(false);
const editName = ref("");
const editDescription = ref("");
const savingDetails = ref(false);

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

async function uploadFiles(files: File[]): Promise<void> {
  if (uploading.value || files.length === 0) {
    return;
  }
  const maxSize = auth.maxFileSize;
  const tooLarge = files.filter((file) => file.size > maxSize);
  const valid = files.filter((file) => file.size <= maxSize);
  if (tooLarge.length > 0) {
    const names = tooLarge.map((file) => file.name).join(", ");
    toast.error(
      `${names} exceed${tooLarge.length === 1 ? "s" : ""} the ${formatBytes(maxSize)} limit`,
    );
  }
  if (valid.length === 0) {
    return;
  }
  uploading.value = true;
  uploads.value = valid.map((file) => ({
    name: file.name,
    progress: 0,
    status: "uploading",
  }));
  let uploaded = 0;
  try {
    for (let index = 0; index < valid.length; index += 1) {
      const item = uploads.value[index];
      try {
        await packagesApi.uploadFile(packageId, valid[index], (fraction) => {
          item.progress = fraction;
        });
        item.progress = 1;
        item.status = "done";
        uploaded += 1;
      } catch (err) {
        item.status = "error";
        toast.error(
          `${item.name}: ${err instanceof ApiError ? err.message : "Upload failed"}`,
        );
      }
    }
    if (uploaded > 0) {
      pkg.value = await packagesApi.get(packageId);
      toast.success(`Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"}`);
    }
  } finally {
    uploading.value = false;
    // Clear the progress list unless something failed (keep failures visible).
    if (uploads.value.every((item) => item.status === "done")) {
      uploads.value = [];
    }
  }
}

function onUpload(event: Event): void {
  const target = event.target as HTMLInputElement;
  const files = target.files ? Array.from(target.files) : [];
  void uploadFiles(files);
  target.value = "";
}

function onDrop(event: DragEvent): void {
  dragging.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    void uploadFiles(Array.from(files));
  }
}

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
  try {
    await packagesApi.removeFile(packageId, fileId);
    pkg.value = await packagesApi.get(packageId);
    toast.success("File removed");
  } catch (err) {
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
  try {
    await packagesApi.removeAllFiles(packageId);
    pkg.value = await packagesApi.get(packageId);
    toast.success("All files removed");
  } catch (err) {
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

async function enableSharing(): Promise<void> {
  try {
    share.value = await sharesApi.enable(
      packageId,
      visibility.value,
      parseEmailList(emailsText.value),
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
  try {
    await navigator.clipboard.writeText(shareLink.value);
    toast.success("Link copied to clipboard");
  } catch {
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

            <ul v-if="uploads.length" class="space-y-2">
              <li v-for="(item, index) in uploads" :key="index" class="space-y-1">
                <div class="flex items-center justify-between gap-2 text-xs">
                  <span class="min-w-0 truncate">{{ item.name }}</span>
                  <span
                    class="shrink-0"
                    :class="
                      item.status === 'error' ? 'text-destructive' : 'text-muted-foreground'
                    "
                  >
                    {{ item.status === "error" ? "Failed" : Math.round(item.progress * 100) + "%" }}
                  </span>
                </div>
                <div class="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="item.status === 'error' ? 'bg-destructive' : 'bg-primary'"
                    :style="{ width: `${Math.round(item.progress * 100)}%` }"
                  />
                </div>
              </li>
            </ul>

            <div v-if="pkg.files.length" class="flex flex-wrap gap-2">
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
            </div>

            <ul v-if="pkg.files.length" class="divide-y rounded-md border">
              <li
                v-for="file in pkg.files"
                :key="file.id"
                class="flex items-center justify-between gap-3 p-3"
              >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium">{{ file.filename }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ formatBytes(file.size) }}
                    <span v-if="stats">
                      &middot; {{ fileDownloads(file.id) }} download{{
                        fileDownloads(file.id) === 1 ? "" : "s"
                      }}
                    </span>
                  </p>
                </div>
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
                <p class="text-xs" :class="share.is_enabled ? 'text-green-600' : 'text-muted-foreground'">
                  {{ share.is_enabled ? "Sharing is active" : "Sharing is paused" }}
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

