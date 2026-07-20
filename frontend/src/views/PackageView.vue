<script setup lang="ts">
import { computed, onMounted, ref, type ComponentPublicInstance } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  Calendar,
  Download,
  FolderUp,
  Pencil,
  QrCode as QrCodeIcon,
  RotateCw,
  Share2,
  Trash2,
  Upload,
  X,
} from "@lucide/vue";
import { packagesApi, sharesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { Package, PackageFile, PackageStats, Share, Visibility } from "@/api/types";
import { formatBytes, formatDuration, formatRate, formatRelativeTime } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { copyText, shareOrCopy } from "@/lib/clipboard";
import { fileIcon } from "@/lib/fileIcon";
import { invalidEmails, parseEmailList } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import { useConfirm } from "@/composables/useConfirm";
import { useUploads, type UploadItem } from "@/composables/useUploads";
import { useArchiveDownload } from "@/composables/useArchiveDownload";
import {
  useResumableUploads,
  type PendingResume,
} from "@/composables/useResumableUploads";
import { setDocumentTitle } from "@/composables/useDocumentTitle";
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
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);
const showQr = ref(false);
const qr = ref<InstanceType<typeof QrCode> | null>(null);

// Upload state lives in a module-level composable, keyed by package id, so a
// running upload's progress is preserved when the user leaves this package and
// comes back to it.
const { uploadsFor, isUploading, uploadRateFor, startUploads, cancelUpload, retryUpload, retryAllFailed, dismissUpload, bindUploaded } =
  useUploads();
const uploads = uploadsFor(packageId);
const uploading = isUploading(packageId);
const uploadRate = uploadRateFor(packageId);

// Archive (zip) download of the whole package (or a selection) with an in-app
// progress read-out; falls back to a native browser download when too large to
// stream in memory.
const {
  downloading: archiving,
  percent: archivePercent,
  indeterminate: archiveIndeterminate,
  bytesPerSecond: archiveRate,
  etaSeconds: archiveEta,
  start: startArchive,
  cancel: cancelArchive,
} = useArchiveDownload();

// Interrupted uploads (whose chunked session survives in localStorage) surfaced
// after a full page reload, so the user can resume or discard each one.
const {
  pending: resumables,
  refresh: refreshResumables,
  remove: removeResumable,
  discard: discardResumableEntry,
} = useResumableUploads(packageId);
const resumeInput = ref<HTMLInputElement | null>(null);
const resumeTarget = ref<PendingResume | null>(null);

// Aggregate progress across the current batch, for the summary bar above the
// per-file rows.
const uploadSummary = computed(() => {
  const items = uploads.value;
  const total = items.length;
  if (total === 0) {
    return null;
  }
  let progressSum = 0;
  let done = 0;
  let failed = 0;
  for (const item of items) {
    progressSum += item.progress;
    if (item.status === "done") {
      done += 1;
    } else if (item.status === "error" || item.status === "canceled") {
      failed += 1;
    }
  }
  return {
    total,
    done,
    failed,
    percent: Math.round((progressSum / total) * 100),
  };
});

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

// Human-friendly "in 3 days" / "2 hours ago" phrasing for the share expiry.
const expiryRelative = computed(() => formatRelativeTime(share.value?.expires_at));

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
    setDocumentTitle(pkg.value.name, pkg.value.description ?? undefined);
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
  if (files.length === 0) {
    return;
  }
  // Reject a batch that would exceed the per-package file cap up front, so the
  // user gets one clear message instead of a 400 toast per overflowing file.
  const current = pkg.value?.files.length ?? 0;
  const max = auth.maxFilesPerPackage;
  if (max > 0 && current + files.length > max) {
    const remaining = Math.max(0, max - current);
    toast.error(
      remaining === 0
        ? `This package already has the maximum of ${max} files.`
        : `You can add ${remaining} more file${remaining === 1 ? "" : "s"} (limit ${max}).`,
    );
    return;
  }
  void startUploads(
    packageId,
    files,
    auth.maxFileSize,
    pkg.value?.name ?? "",
    appendUploadedFile,
  );
}

function onUpload(event: Event): void {
  const target = event.target as HTMLInputElement;
  const files = target.files ? Array.from(target.files) : [];
  runUploads(files);
  target.value = "";
}

// Folder picker: browsers expose every file under the chosen directory via the
// same FileList. Names are flattened server-side (the stored filename keeps the
// leaf name), so a whole folder can be added in one action.
function onFolderUpload(event: Event): void {
  const target = event.target as HTMLInputElement;
  const files = target.files ? Array.from(target.files) : [];
  runUploads(files);
  target.value = "";
}

// `webkitdirectory` / `directory` are not standard, typed input attributes, so
// set them imperatively on the element via a function ref (which also captures
// the ref used to open the picker).
function setFolderInput(
  el: Element | ComponentPublicInstance | null,
): void {
  const input = el instanceof HTMLInputElement ? el : null;
  folderInput.value = input;
  if (input) {
    input.setAttribute("webkitdirectory", "");
    input.setAttribute("directory", "");
  }
}

function onDrop(event: DragEvent): void {
  dragging.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    runUploads(Array.from(files));
  }
}

/** Percent of an interrupted upload already received by the server. */
function resumePercent(entry: PendingResume): number {
  return entry.size > 0 ? Math.round((entry.offset / entry.size) * 100) : 0;
}

/** Open the file picker so the user can re-select a file to resume. */
function pickResume(entry: PendingResume): void {
  resumeTarget.value = entry;
  resumeInput.value?.click();
}

/**
 * Resume an interrupted upload once the user re-selects the original file. The
 * chosen file must match the stored signature (name, size, last-modified) so we
 * never append bytes from a different file onto an existing server session; the
 * chunked-upload flow then continues from the server's received offset.
 */
function onResumeFile(event: Event): void {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  target.value = "";
  const entry = resumeTarget.value;
  resumeTarget.value = null;
  if (!file || !entry) {
    return;
  }
  if (
    file.name !== entry.filename ||
    file.size !== entry.size ||
    file.lastModified !== entry.lastModified
  ) {
    toast.error(
      `That file doesn't match \u201c${entry.filename}\u201d. Choose the original file to resume.`,
    );
    return;
  }
  removeResumable(entry.key);
  runUploads([file]);
}

/** Abort and forget an interrupted upload the user does not want to resume. */
function discardResume(entry: PendingResume): void {
  void discardResumableEntry(entry);
}

/**
 * Append a just-uploaded file to the list in place (optimistic), skipping any
 * duplicate id. Used as the upload callback so a finished file appears
 * immediately instead of refetching the whole package after the batch.
 */
function appendUploadedFile(file: PackageFile): void {
  const current = pkg.value;
  if (!current || current.files.some((existing) => existing.id === file.id)) {
    return;
  }
  current.files = [...current.files, file];
}

/**
 * Optimistically apply `mutate` to the current file list, run `apiCall`, and on
 * failure restore the previous list and surface `failMessage`. Centralises the
 * snapshot/restore that every file-removal action needs.
 */
async function optimisticFileUpdate(
  mutate: (files: PackageFile[]) => PackageFile[],
  apiCall: () => Promise<void>,
  successMessage: string,
  failMessage: string,
): Promise<void> {
  const current = pkg.value;
  if (!current) {
    return;
  }
  const previous = current.files;
  current.files = mutate(previous);
  try {
    await apiCall();
    toast.success(successMessage);
  } catch (err) {
    current.files = previous;
    toast.error(err instanceof ApiError ? err.message : failMessage);
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
  if (selectedFiles.value.has(fileId)) {
    const nextSelected = new Set(selectedFiles.value);
    nextSelected.delete(fileId);
    selectedFiles.value = nextSelected;
  }
  await optimisticFileUpdate(
    (files) => files.filter((file) => file.id !== fileId),
    () => packagesApi.removeFile(packageId, fileId),
    "File removed",
    "Failed to remove file",
  );
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
  selectedFiles.value = new Set();
  await optimisticFileUpdate(
    () => [],
    () => packagesApi.removeAllFiles(packageId),
    "All files removed",
    "Failed to remove files",
  );
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
  const idSet = new Set(ids);
  selectedFiles.value = new Set();
  await optimisticFileUpdate(
    (files) => files.filter((file) => !idSet.has(file.id)),
    () => packagesApi.removeAllFiles(packageId, ids),
    "Files removed",
    "Failed to remove files",
  );
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

/** Fetch a one-shot token, then stream the zip with an in-app progress bar. */
async function ownerArchiveDownload(
  estimatedBytes: number,
  ids: number[],
): Promise<void> {
  try {
    const { token } = await packagesApi.downloadToken(packageId);
    const url = packagesApi.downloadAllUrl(
      packageId,
      token,
      ids.length > 0 ? ids : undefined,
    );
    const outcome = await startArchive(
      url,
      `${pkg.value?.name ?? "package"}.zip`,
      estimatedBytes,
    );
    if (outcome === "fell-back") {
      toast.info("Download started");
    }
  } catch {
    toast.error("Failed to download files");
  }
}

async function downloadAllOwned(): Promise<void> {
  const files = pkg.value?.files ?? [];
  if (files.length === 0) {
    return;
  }
  await ownerArchiveDownload(
    files.reduce((sum, file) => sum + file.size, 0),
    [],
  );
}

function downloadSelectedOwned(): void {
  const ids = Array.from(selectedFiles.value);
  if (ids.length === 0) {
    return;
  }
  const bytes = (pkg.value?.files ?? [])
    .filter((file) => selectedFiles.value.has(file.id))
    .reduce((sum, file) => sum + file.size, 0);
  void ownerArchiveDownload(bytes, ids);
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

// Offer the OS share sheet on mobile (Web Share API) and fall back to copying
// the link on desktop browsers that don't support it.
async function sharePackage(): Promise<void> {
  const result = await shareOrCopy({
    url: shareLink.value,
    title: pkg.value?.name,
    text: pkg.value ? `Files shared with you: ${pkg.value.name}` : undefined,
  });
  if (result === "copied") {
    toast.success("Link copied to clipboard");
  } else if (result === "failed") {
    toast.error("Couldn't share the link");
  }
}

async function downloadQr(): Promise<void> {
  const base = pkg.value?.name?.trim() || "share";
  try {
    await qr.value?.download(`${base}-qr.png`);
  } catch {
    toast.error("Couldn't export the QR code");
  }
}

onMounted(() => {
  void load();
  // Re-attach the optimistic-append callback so a view that was navigated away
  // from and back to mid-upload still reflects files finished by the running
  // batch (which was started with the previous instance's callback).
  bindUploaded(packageId, appendUploadedFile);
  // Surface any upload interrupted before a full reload so it can be resumed.
  void refreshResumables();
});
</script>

<template>
  <div class="space-y-4">
    <Button variant="ghost" size="sm" @click="router.push('/dashboard')">
      <ArrowLeft class="h-4 w-4" /> Back
    </Button>

    <Alert v-if="error" kind="error">{{ error }}</Alert>

    <div v-if="loading" class="space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div class="min-w-0 space-y-2">
          <Skeleton class="h-8 w-48 max-w-full" />
          <Skeleton class="h-4 w-64 max-w-full" />
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
        <Card class="min-w-0">
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
            <!-- webkitdirectory is set imperatively (not a standard typed
                 attribute) so a whole folder can be selected at once. -->
            <input
              :ref="setFolderInput"
              type="file"
              multiple
              class="hidden"
              @change="onFolderUpload"
            />
            <!-- Single-file picker for resuming an interrupted upload: the
                 browser cannot re-open the original file after a reload, so the
                 user re-selects it and we match it to the stored session. -->
            <input
              ref="resumeInput"
              type="file"
              class="hidden"
              @change="onResumeFile"
            />

            <div
              v-if="resumables.length"
              class="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3"
            >
              <p class="text-sm font-medium">Resume interrupted upload</p>
              <ul class="space-y-2">
                <li
                  v-for="entry in resumables"
                  :key="entry.key"
                  class="flex items-center justify-between gap-3 text-sm"
                >
                  <span class="min-w-0 flex-1 truncate">
                    {{ entry.filename }}
                    <span class="text-muted-foreground">
                      &middot; {{ resumePercent(entry) }}% uploaded
                    </span>
                  </span>
                  <span class="flex shrink-0 gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      class="h-8 gap-1.5 px-2.5 text-xs"
                      :disabled="uploading"
                      @click="pickResume(entry)"
                    >
                      <RotateCw class="h-4 w-4" /> Resume
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      class="h-8 gap-1.5 px-2.5 text-xs text-muted-foreground"
                      @click="discardResume(entry)"
                    >
                      <X class="h-4 w-4" /> Discard
                    </Button>
                  </span>
                </li>
              </ul>
            </div>

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

            <div class="flex justify-center">
              <Button
                variant="ghost"
                size="sm"
                :disabled="uploading"
                @click="folderInput?.click()"
              >
                <FolderUp class="h-4 w-4" /> Upload a folder
              </Button>
            </div>

            <div v-if="uploadSummary" class="space-y-1.5">
              <div class="flex items-center justify-between gap-2 text-xs">
                <span class="min-w-0 truncate font-medium">
                  {{ uploading ? "Uploading\u2026" : "Upload complete" }}
                  {{ uploadSummary.done }}/{{ uploadSummary.total }}
                  <span v-if="uploadSummary.failed > 0" class="text-destructive">
                    &middot; {{ uploadSummary.failed }} failed
                  </span>
                </span>
                <span class="shrink-0 tabular-nums text-muted-foreground">
                  {{ uploadSummary.percent }}%
                </span>
              </div>
              <div
                class="h-1.5 overflow-hidden rounded-full bg-muted"
                role="progressbar"
                :aria-valuenow="uploadSummary.percent"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-label="Overall upload progress"
              >
                <div
                  class="h-full rounded-full bg-primary transition-all"
                  :style="{ width: `${uploadSummary.percent}%` }"
                />
              </div>
              <div
                v-if="uploading && uploadRate.bytesPerSecond > 0"
                class="flex items-center justify-between gap-2 text-xs text-muted-foreground"
              >
                <span class="tabular-nums">{{ formatRate(uploadRate.bytesPerSecond) }}</span>
                <span v-if="formatDuration(uploadRate.etaSeconds)" class="tabular-nums">
                  {{ formatDuration(uploadRate.etaSeconds) }} left
                </span>
              </div>
              <div v-if="!uploading && uploadSummary.failed > 0">
                <Button
                  variant="outline"
                  size="sm"
                  class="h-8 gap-1.5 px-2.5 text-xs"
                  @click="retryAllFailed(packageId)"
                >
                  <RotateCw class="h-4 w-4" /> Retry all failed
                </Button>
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
                  :disabled="archiving"
                  @click="downloadAllOwned"
                >
                  <Download class="h-4 w-4" />
                  {{ archiving ? "Preparing…" : "Download all" }}
                </Button>
                <Button variant="destructive" :disabled="archiving" @click="removeAllFiles">
                  <Trash2 class="h-4 w-4" /> Delete all
                </Button>
                <template v-if="hasFileSelection">
                  <Button variant="secondary" :disabled="archiving" @click="downloadSelectedOwned">
                    <Download class="h-4 w-4" /> Download {{ selectedFiles.size }} selected
                  </Button>
                  <Button variant="destructive" :disabled="archiving" @click="deleteSelectedFiles">
                    <Trash2 class="h-4 w-4" /> Delete {{ selectedFiles.size }} selected
                  </Button>
                </template>
              </div>

              <div v-if="archiving" class="space-y-1">
                <div class="flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    Preparing download…
                    <span v-if="formatRate(archiveRate)" class="tabular-nums">
                      &middot; {{ formatRate(archiveRate) }}
                    </span>
                    <span v-if="formatDuration(archiveEta)" class="tabular-nums">
                      &middot; {{ formatDuration(archiveEta) }} left
                    </span>
                  </span>
                  <div class="flex items-center gap-2">
                    <span v-if="archivePercent !== null" class="tabular-nums">
                      {{ archivePercent }}%
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      class="h-6 px-2 text-xs"
                      @click="cancelArchive"
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
                <div
                  class="h-1.5 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  :aria-valuenow="archivePercent ?? undefined"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  aria-label="Preparing archive download"
                >
                  <div
                    class="h-full rounded-full bg-primary transition-[width]"
                    :class="archiveIndeterminate ? 'w-1/3 animate-pulse' : ''"
                    :style="archiveIndeterminate ? undefined : { width: `${archivePercent ?? 0}%` }"
                  />
                </div>
              </div>

              <div class="flex flex-col gap-2 sm:flex-row">
                <Input
                  v-model="fileFilter"
                  placeholder="Filter files..."
                  class="sm:flex-1"
                />
                <select
                  v-model="fileSort"
                  aria-label="Sort files"
                  class="h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:w-44"
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

        <Card class="min-w-0">
          <CardHeader>
            <CardTitle>Sharing</CardTitle>
            <CardDescription>
              Sharing is off by default. Enable it to generate a secure link.
            </CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <Label>Visibility</Label>
              <div class="flex flex-wrap gap-x-4 gap-y-2">
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
                  <Button variant="secondary" class="shrink-0 gap-1.5" @click="sharePackage">
                    <Share2 class="h-4 w-4" /> Share
                  </Button>
                  <Button variant="outline" class="shrink-0" @click="copyLink">
                    Copy
                  </Button>
                </div>
                <div class="pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    class="gap-1.5"
                    :aria-expanded="showQr"
                    aria-controls="share-qr"
                    @click="showQr = !showQr"
                  >
                    <QrCodeIcon class="h-4 w-4" />
                    {{ showQr ? "Hide QR code" : "Show QR code" }}
                  </Button>
                  <div
                    v-if="showQr"
                    id="share-qr"
                    class="mt-3 flex flex-col items-center gap-3 rounded-md border p-4 text-center"
                  >
                    <QrCode ref="qr" :value="shareLink" label="QR code for the share link" />
                    <p class="text-xs text-muted-foreground">
                      Scan to open the share link on another device.
                    </p>
                    <Button
                      variant="secondary"
                      size="sm"
                      class="gap-1.5"
                      @click="downloadQr"
                    >
                      <Download class="h-4 w-4" /> Download PNG
                    </Button>
                  </div>
                </div>
                <p class="text-xs" :class="share.is_enabled ? 'text-green-600' : 'text-muted-foreground'">
                  {{ share.is_enabled ? "Sharing is active" : "Sharing is paused" }}
                </p>
                <p
                  v-if="expiryLabel"
                  class="flex flex-wrap items-center gap-1 text-xs"
                  :class="shareExpired ? 'text-destructive' : 'text-muted-foreground'"
                >
                  <Calendar class="h-3 w-3" />
                  <span>{{ shareExpired ? "Expired" : "Expires" }} {{ expiryRelative }}</span>
                  <span class="text-muted-foreground">· {{ expiryLabel }}</span>
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

