<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Download, Pencil, Trash2, Upload } from "lucide-vue-next";
import { packagesApi, sharesApi } from "@/api";
import { ApiError, getToken } from "@/api/client";
import type { Package, Share, Visibility } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { downloadBlob } from "@/lib/download";
import { invalidEmails } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import { useConfirm } from "@/composables/useConfirm";
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
  Tooltip,
} from "@/components/ui";

const route = useRoute();
const router = useRouter();
const toast = useToasts();
const { confirm } = useConfirm();
const packageId = Number(route.params.id);

const pkg = ref<Package | null>(null);
const share = ref<Share | null>(null);
const error = ref<string | null>(null);
const loading = ref(true);
const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

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

const emailIssues = computed(() => invalidEmails(emailsText.value));
const restrictedEmailsOk = computed(
  () =>
    visibility.value !== "restricted" ||
    (parseEmails().length > 0 && emailIssues.value.length === 0),
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

async function onUpload(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (!files || files.length === 0) {
    return;
  }
  uploading.value = true;
  try {
    let count = 0;
    for (const file of Array.from(files)) {
      await packagesApi.uploadFile(packageId, file);
      count += 1;
    }
    pkg.value = await packagesApi.get(packageId);
    toast.success(`Uploaded ${count} file${count === 1 ? "" : "s"}`);
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Upload failed");
  } finally {
    uploading.value = false;
    if (fileInput.value) {
      fileInput.value.value = "";
    }
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

function downloadOwned(fileId: number, filename: string): void {
  const token = getToken();
  fetch(`/api/packages/${packageId}/files/${fileId}/download`, {
    headers: token ? { Authorization: "Bearer " + token } : {},
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Download failed");
      }
      return response.blob();
    })
    .then((blob) => downloadBlob(blob, filename))
    .catch(() => toast.error("Failed to download file"));
}

async function enableSharing(): Promise<void> {
  try {
    share.value = await sharesApi.enable(packageId, visibility.value, parseEmails());
    toast.success("Sharing enabled");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to enable sharing");
  }
}

async function updateSharing(): Promise<void> {
  try {
    share.value = await sharesApi.update(packageId, {
      visibility: visibility.value,
      allowed_emails: parseEmails(),
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
  <div class="space-y-6">
    <Button variant="ghost" size="sm" @click="router.push('/dashboard')">
      <ArrowLeft class="h-4 w-4" /> Back
    </Button>

    <Alert v-if="error" kind="error">{{ error }}</Alert>
    <p v-if="loading" class="text-muted-foreground">Loading...</p>

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
              class="flex items-center justify-between gap-3 p-3"
            >
              <div class="min-w-0">
                <p class="truncate text-sm font-medium">{{ file.filename }}</p>
                <p class="text-xs text-muted-foreground">{{ formatBytes(file.size) }}</p>
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
    </template>
  </div>
</template>
