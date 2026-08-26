<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from "reka-ui";
import {
  FileArchive,
  FolderUp,
  HardDrive,
  Loader2,
  Plus,
  RotateCw,
  Search,
  Share2,
  Upload,
  X,
} from "@lucide/vue";
import { authApi, packagesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PackageListItem, StorageUsage } from "@/api/types";
import { dialogOverlayClass, responsiveDialogContentClass } from "@/lib/dialog";
import { formatBytes } from "@/lib/format";
import { useToasts } from "@/composables/useToasts";
import { useFilePicker } from "@/composables/useFilePicker";
import { useUploads } from "@/composables/useUploads";
import { useAuthStore } from "@/stores/auth";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  Label,
  Pagination,
  Skeleton,
} from "@/components/ui";

const toast = useToasts();
const router = useRouter();
const auth = useAuthStore();
const { startUploads } = useUploads();

const packages = ref<PackageListItem[]>([]);
const total = ref(0);
const offset = ref(0);
const pageSize = 12;
const loading = ref(true);
// A later fetch (search / pagination) keeps the current list on screen under a
// subtle spinner instead of replacing it with skeletons, so the page never
// flashes empty on every keystroke or page change.
const refetching = ref(false);
const loaded = ref(false);
const error = ref<string | null>(null);

const search = ref("");
const usage = ref<StorageUsage | null>(null);

type CreationMode = "upload" | "empty";

const createDialogOpen = ref(false);
const creationMode = ref<CreationMode>("upload");
const name = ref("");
const description = ref("");
const creating = ref(false);
const uploadModeButton = ref<HTMLButtonElement | null>(null);
const packageNameInput = ref<InstanceType<typeof Input> | null>(null);
const {
  dragging,
  setFileInput,
  setFolderInput,
  onPick: onPickCreate,
  onDrop: onDropCreate,
  openFiles,
  openFolder,
} = useFilePicker(createFromFiles);

const usagePercent = computed(() => {
  const current = usage.value;
  if (!current || current.storage_quota <= 0) {
    return 0;
  }
  return Math.min(
    100,
    Math.round((current.storage_used / current.storage_quota) * 100),
  );
});

async function load(): Promise<void> {
  // Show full skeletons only on the very first load; subsequent loads keep the
  // current list visible under a refetch spinner (see `refetching`).
  if (loaded.value) {
    refetching.value = true;
  } else {
    loading.value = true;
  }
  error.value = null;
  try {
    const page = await packagesApi.list({
      limit: pageSize,
      offset: offset.value,
      q: search.value,
    });
    packages.value = page.items;
    total.value = page.total;
    loaded.value = true;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load packages";
  } finally {
    loading.value = false;
    refetching.value = false;
  }
}

async function loadUsage(): Promise<void> {
  try {
    usage.value = await authApi.usage();
  } catch {
    usage.value = null;
  }
}

// Debounce search so typing doesn't fire a request per keystroke; reset to the
// first page whenever the query changes.
let searchTimer: ReturnType<typeof setTimeout> | undefined;
watch(search, () => {
  if (searchTimer) {
    clearTimeout(searchTimer);
  }
  searchTimer = setTimeout(() => {
    offset.value = 0;
    void load();
  }, 300);
});

function goToOffset(nextOffset: number): void {
  offset.value = nextOffset;
  void load();
}

function onCreateDialogOpenChange(open: boolean): void {
  if (!open && creating.value) {
    return;
  }
  createDialogOpen.value = open;
  if (!open) {
    creationMode.value = "upload";
    name.value = "";
    description.value = "";
    dragging.value = false;
  }
}

function onCreateDialogOpenAutoFocus(event: Event): void {
  event.preventDefault();
  if (creationMode.value === "upload") {
    uploadModeButton.value?.focus();
  } else {
    packageNameInput.value?.focus();
  }
}

async function create(): Promise<void> {
  if (!name.value.trim()) {
    toast.warning("Package name is required");
    return;
  }
  creating.value = true;
  try {
    const created = await packagesApi.create(name.value.trim(), description.value || null);
    toast.success(`Created "${created.name}"`);
    await router.push({ name: "package", params: { id: created.id } });
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to create package");
  } finally {
    creating.value = false;
  }
}

// --- Create-package-on-drop -------------------------------------------------
// Dropping (or picking) files or a folder creates a package and starts the
// uploads in one step, cutting the "create, open, then upload" flow down to a
// single action. The uploads run in the module-level composable, so they keep
// going as we navigate into the new package.
/** Name a dropped batch after its folder or first file. */
function defaultPackageName(files: File[]): string {
  const withPath = files.find((file) => file.webkitRelativePath);
  const top = withPath?.webkitRelativePath.split("/")[0];
  if (top) {
    return top;
  }
  const firstName = files[0]?.name ?? "Upload";
  if (files.length === 1) {
    return firstName;
  }
  const suffix = ` + ${files.length - 1} more`;
  return `${firstName.slice(0, 255 - suffix.length)}${suffix}`;
}

async function createFromFiles(files: File[]): Promise<void> {
  if (files.length === 0 || creating.value) {
    return;
  }
  const max = auth.maxFilesPerPackage;
  if (max > 0 && files.length > max) {
    toast.error(`A package can hold at most ${max} files.`);
    return;
  }
  creating.value = true;
  try {
    const created = await packagesApi.create(defaultPackageName(files), null);
    void startUploads(created.id, files, auth.maxFileSize, created.name);
    toast.success(`Created "${created.name}" — uploading ${files.length} file(s)`);
    await router.push({ name: "package", params: { id: created.id } });
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to create package");
  } finally {
    creating.value = false;
  }
}

onMounted(() => {
  void load();
  void loadUsage();
});
</script>

<template>
  <div class="mx-auto w-full max-w-[96rem] space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="space-y-1">
        <h1 class="text-2xl font-bold">Your packages</h1>
        <p class="text-muted-foreground">Create packages and share them securely</p>
      </div>
      <DialogRoot :open="createDialogOpen" @update:open="onCreateDialogOpenChange">
        <DialogTrigger as-child>
          <Button id="new-package-button" class="w-full sm:w-auto">
            <Plus class="h-4 w-4" />
            New package
          </Button>
        </DialogTrigger>
        <DialogPortal>
          <DialogOverlay :class="dialogOverlayClass" />
          <DialogContent
            id="create-package-dialog"
            :class="responsiveDialogContentClass('lg')"
            @open-auto-focus="onCreateDialogOpenAutoFocus"
            @escape-key-down="onCreateDialogOpenChange(false)"
          >
            <div class="pr-10">
              <DialogTitle class="text-xl font-semibold">New package</DialogTitle>
              <DialogDescription class="mt-1 text-sm text-muted-foreground">
                Upload files now or start with an empty package.
              </DialogDescription>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              class="absolute right-4 top-4"
              :disabled="creating"
              aria-label="Close create package dialog"
              @click="onCreateDialogOpenChange(false)"
            >
              <X class="h-4 w-4" />
            </Button>

            <div
              class="mt-6 grid grid-cols-2 gap-1 rounded-md bg-muted p-1"
              aria-label="Package creation method"
            >
              <button
                ref="uploadModeButton"
                type="button"
                class="flex min-h-10 items-center justify-center gap-2 rounded-sm px-3 text-sm font-medium transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
                :class="creationMode === 'upload'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'"
                :aria-pressed="creationMode === 'upload'"
                :disabled="creating"
                @click="creationMode = 'upload'"
              >
                <Upload class="h-4 w-4" />
                Upload files
              </button>
              <button
                type="button"
                class="flex min-h-10 items-center justify-center gap-2 rounded-sm px-3 text-sm font-medium transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
                :class="creationMode === 'empty'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'"
                :aria-pressed="creationMode === 'empty'"
                :disabled="creating"
                @click="creationMode = 'empty'"
              >
                <Plus class="h-4 w-4" />
                Empty package
              </button>
            </div>

            <div v-if="creationMode === 'upload'" class="mt-5 space-y-4">
              <div
                class="flex min-h-40 flex-col items-center justify-center rounded-md border border-dashed px-5 py-6 text-center transition-colors"
                :class="[
                  dragging ? 'border-primary bg-primary/5' : 'border-input bg-background/50',
                  creating ? 'pointer-events-none opacity-60' : '',
                ]"
                @dragover.prevent="dragging = true"
                @dragenter.prevent="dragging = true"
                @dragleave.prevent="dragging = false"
                @drop.prevent="onDropCreate"
              >
                <span
                  class="mb-3 flex h-10 w-10 items-center justify-center rounded-md border bg-background text-primary"
                >
                  <Loader2 v-if="creating" class="h-5 w-5 animate-spin" />
                  <Upload v-else class="h-5 w-5" />
                </span>
                <p class="hidden text-sm font-medium md:block">
                  Drop files or a folder here
                </p>
                <p class="text-sm font-medium md:hidden">Choose files or a folder</p>
                <p class="mt-1 text-xs text-muted-foreground">
                  A package is named automatically and starts uploading right away.
                </p>
              </div>
              <div class="grid grid-cols-2 gap-2">
                <Button
                  class="w-full"
                  :disabled="creating"
                  @click="openFiles"
                >
                  <Upload class="h-4 w-4" />
                  Choose files
                </Button>
                <Button
                  variant="outline"
                  class="w-full"
                  :disabled="creating"
                  @click="openFolder"
                >
                  <FolderUp class="h-4 w-4" />
                  Choose folder
                </Button>
              </div>
            </div>

            <form v-else class="mt-5 space-y-5" @submit.prevent="create">
              <div class="space-y-2">
                <Label for="pkg-name">Name</Label>
                <Input
                  id="pkg-name"
                  ref="packageNameInput"
                  v-model="name"
                  placeholder="Project assets"
                />
              </div>
              <div class="space-y-2">
                <Label for="pkg-desc">Description</Label>
                <textarea
                  id="pkg-desc"
                  v-model="description"
                  rows="3"
                  placeholder="Optional"
                  class="flex min-h-24 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              <div class="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  :disabled="creating"
                  @click="onCreateDialogOpenChange(false)"
                >
                  Cancel
                </Button>
                <Button type="submit" :disabled="creating">
                  {{ creating ? "Creating..." : "Create package" }}
                </Button>
              </div>
            </form>
          </DialogContent>
        </DialogPortal>
      </DialogRoot>
    </div>

    <input
      :ref="setFileInput"
      type="file"
      multiple
      class="hidden"
      @change="onPickCreate"
    />
    <!-- webkitdirectory is set imperatively (not a standard typed attribute) so
         a whole folder can be picked to create a package from it. -->
    <input
      :ref="setFolderInput"
      type="file"
      multiple
      class="hidden"
      @change="onPickCreate"
    />

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <section aria-labelledby="packages-heading" class="min-w-0 space-y-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="packages-heading" class="text-lg font-semibold">Packages</h2>
            <p v-if="!loading && !error" class="text-sm text-muted-foreground">
              {{ total }} package{{ total === 1 ? "" : "s" }}
            </p>
          </div>
          <div v-if="total > 0 || search.trim()" class="relative w-full sm:max-w-sm">
            <Search
              class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input v-model="search" placeholder="Search packages..." class="pl-9 pr-9" />
            <Loader2
              v-if="refetching"
              class="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground"
              aria-hidden="true"
            />
          </div>
        </div>

        <div v-if="error" class="space-y-3">
          <Alert kind="error">{{ error }}</Alert>
          <Button variant="outline" size="sm" :disabled="refetching" @click="load">
            <RotateCw class="h-4 w-4" :class="refetching ? 'animate-spin' : ''" />
            Try again
          </Button>
        </div>

        <div v-if="loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          <Card v-for="n in 6" :key="n" class="h-full">
            <CardHeader class="space-y-3">
              <Skeleton class="h-9 w-9" />
              <Skeleton class="h-5 w-2/3" />
              <Skeleton class="h-4 w-1/3" />
            </CardHeader>
          </Card>
        </div>

        <EmptyState
          v-else-if="packages.length === 0"
          :icon="FileArchive"
          :heading-level="3"
          :title="search.trim() ? 'No matching packages' : 'No packages yet'"
          :description="search.trim()
            ? `No packages match “${search.trim()}”. Try a different search.`
            : 'Upload files now or create an empty package to get started.'"
        >
          <Button
            v-if="search.trim()"
            variant="outline"
            size="sm"
            @click="search = ''"
          >
            Clear search
          </Button>
          <Button v-else size="sm" @click="createDialogOpen = true">
            <Plus class="h-4 w-4" />
            Create package
          </Button>
        </EmptyState>

        <template v-else>
          <div
            class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
            :class="refetching ? 'pointer-events-none opacity-60 transition-opacity' : ''"
          >
            <RouterLink
              v-for="pkg in packages"
              :key="pkg.id"
              :to="{ name: 'package', params: { id: pkg.id } }"
              class="group min-w-0"
            >
              <Card
                class="h-full transition-[border-color,box-shadow,transform] group-hover:-translate-y-0.5 group-hover:border-primary/60 group-hover:shadow-sm"
              >
                <CardHeader class="space-y-4">
                  <div class="flex items-start justify-between gap-3">
                    <span
                      class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background text-primary"
                    >
                      <FileArchive class="h-4 w-4" />
                    </span>
                    <Share2 class="h-4 w-4 shrink-0 text-muted-foreground" />
                  </div>
                  <div class="min-w-0">
                    <CardTitle class="truncate text-base">{{ pkg.name }}</CardTitle>
                    <CardDescription class="mt-1">
                      {{ pkg.file_count }} {{ pkg.file_count === 1 ? "file" : "files" }}
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent v-if="pkg.description">
                  <p class="line-clamp-2 text-sm text-muted-foreground">
                    {{ pkg.description }}
                  </p>
                </CardContent>
              </Card>
            </RouterLink>
          </div>

          <Pagination
            v-if="total > pageSize"
            :total="total"
            :limit="pageSize"
            :offset="offset"
            :disabled="refetching"
            :label="`${total} package${total === 1 ? '' : 's'}`"
            @update:offset="goToOffset"
          />
        </template>
      </section>

      <aside class="space-y-4 xl:sticky xl:top-6">
        <section
          aria-labelledby="quick-upload-heading"
          class="hidden flex-col items-center rounded-md border border-dashed px-5 py-7 text-center transition-colors xl:flex"
          :class="[
            dragging ? 'border-primary bg-primary/5' : 'border-input bg-card/40',
            creating ? 'pointer-events-none opacity-60' : '',
          ]"
          @dragover.prevent="dragging = true"
          @dragenter.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDropCreate"
        >
          <span
            class="mb-4 flex h-11 w-11 items-center justify-center rounded-md border bg-background text-primary"
          >
            <Upload class="h-5 w-5" />
          </span>
          <h2 id="quick-upload-heading" class="font-semibold">Upload and create</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Drop files or a folder here to create a package and start uploading.
          </p>
          <div class="mt-5 grid w-full grid-cols-2 gap-2">
            <Button
              variant="outline"
              size="sm"
              :disabled="creating"
              @click="openFiles"
            >
              <Upload class="h-4 w-4" /> Files
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="creating"
              @click="openFolder"
            >
              <FolderUp class="h-4 w-4" /> Folder
            </Button>
          </div>
        </section>

        <Card v-if="usage">
          <CardContent class="p-5">
            <div class="mb-4 flex items-center gap-3">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground"
              >
                <HardDrive class="h-4 w-4" />
              </span>
              <div class="min-w-0">
                <h2 class="font-semibold">Storage</h2>
                <p class="truncate text-sm text-muted-foreground">
                  {{ formatBytes(usage.storage_used) }} used
                </p>
              </div>
            </div>
            <div
              v-if="usage.storage_quota > 0"
              class="h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              :aria-valuenow="usagePercent"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-label="Storage used"
            >
              <div
                class="h-full rounded-full transition-all"
                :class="usagePercent >= 90 ? 'bg-destructive' : 'bg-primary'"
                :style="{ width: `${usagePercent}%` }"
              />
            </div>
            <p class="mt-2 text-xs text-muted-foreground">
              <template v-if="usage.storage_quota > 0">
                {{ usagePercent }}% of {{ formatBytes(usage.storage_quota) }}
              </template>
              <template v-else>Unlimited storage</template>
            </p>
          </CardContent>
        </Card>
      </aside>
    </div>
  </div>
</template>
