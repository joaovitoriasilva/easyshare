<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { FileArchive, Plus, Search, Share2, Upload } from "@lucide/vue";
import { authApi, packagesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PackageListItem, StorageUsage } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { useToasts } from "@/composables/useToasts";
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
  Input,
  Label,
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
const error = ref<string | null>(null);

const search = ref("");
const usage = ref<StorageUsage | null>(null);

const showForm = ref(false);
const name = ref("");
const description = ref("");
const creating = ref(false);

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
  loading.value = true;
  error.value = null;
  try {
    const page = await packagesApi.list({
      limit: pageSize,
      offset: offset.value,
      q: search.value,
    });
    packages.value = page.items;
    total.value = page.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load packages";
  } finally {
    loading.value = false;
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

function next(): void {
  if (offset.value + pageSize < total.value) {
    offset.value += pageSize;
    load();
  }
}

function prev(): void {
  if (offset.value > 0) {
    offset.value = Math.max(0, offset.value - pageSize);
    load();
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
const dragging = ref(false);
const dropInput = ref<HTMLInputElement | null>(null);

/** Name a dropped batch after its top-level folder, else a dated fallback. */
function defaultPackageName(files: File[]): string {
  const withPath = files.find((file) => file.webkitRelativePath);
  const top = withPath?.webkitRelativePath.split("/")[0];
  return top || `Upload ${new Date().toLocaleDateString()}`;
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

function onDropCreate(event: DragEvent): void {
  dragging.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    void createFromFiles(Array.from(files));
  }
}

function onPickCreate(event: Event): void {
  const target = event.target as HTMLInputElement;
  const files = target.files ? Array.from(target.files) : [];
  void createFromFiles(files);
  target.value = "";
}

onMounted(() => {
  void load();
  void loadUsage();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold">Your packages</h1>
        <p class="text-muted-foreground">Create packages and share them securely</p>
      </div>
      <Button class="w-full sm:w-auto" @click="showForm = !showForm">
        <Plus class="h-4 w-4" /> New package
      </Button>
    </div>

    <input
      ref="dropInput"
      type="file"
      multiple
      class="hidden"
      @change="onPickCreate"
    />
    <div
      role="button"
      tabindex="0"
      aria-label="Create a package from files"
      class="flex flex-col items-center justify-center rounded-md border border-dashed px-4 py-6 text-center transition-colors"
      :class="[
        dragging ? 'border-primary bg-primary/5' : 'border-input',
        creating ? 'pointer-events-none opacity-60' : 'cursor-pointer hover:border-primary',
      ]"
      @click="dropInput?.click()"
      @keydown.enter.prevent="dropInput?.click()"
      @keydown.space.prevent="dropInput?.click()"
      @dragover.prevent="dragging = true"
      @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDropCreate"
    >
      <div class="pointer-events-none flex flex-col items-center gap-1">
        <Upload class="h-6 w-6 text-muted-foreground" />
        <p class="text-sm">
          <span class="font-medium text-primary">Drop files here</span>
          to create a package
        </p>
        <p class="text-xs text-muted-foreground">
          A new package is created and your files start uploading right away.
        </p>
      </div>
    </div>

    <Card v-if="usage">
      <CardContent class="py-4">
        <div class="mb-2 flex items-center justify-between gap-2 text-sm">
          <span class="text-muted-foreground">Storage used</span>
          <span class="font-medium">
            {{ formatBytes(usage.storage_used) }}
            <template v-if="usage.storage_quota > 0">
              of {{ formatBytes(usage.storage_quota) }} ({{ usagePercent }}%)
            </template>
            <span v-else class="font-normal text-muted-foreground">(unlimited)</span>
          </span>
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
      </CardContent>
    </Card>

    <div v-if="total > 0 || search.trim()" class="relative">
      <Search
        class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input v-model="search" placeholder="Search packages..." class="pl-9" />
    </div>

    <Card v-if="showForm">
      <CardHeader>
        <CardTitle>Create a package</CardTitle>
        <CardDescription>Give your package a name and optional description.</CardDescription>
      </CardHeader>
      <form @submit.prevent="create">
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="pkg-name">Name</Label>
            <Input id="pkg-name" v-model="name" placeholder="Project assets" />
          </div>
          <div class="space-y-2">
            <Label for="pkg-desc">Description</Label>
            <Input id="pkg-desc" v-model="description" placeholder="Optional" />
          </div>
          <Button type="submit" :disabled="creating">
            {{ creating ? "Creating..." : "Create" }}
          </Button>
        </CardContent>
      </form>
    </Card>

    <Alert v-if="error" kind="error">{{ error }}</Alert>

    <div v-if="loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card v-for="n in 6" :key="n" class="h-full">
        <CardHeader class="space-y-3">
          <Skeleton class="h-5 w-2/3" />
          <Skeleton class="h-4 w-1/3" />
        </CardHeader>
      </Card>
    </div>

    <div v-else-if="packages.length === 0" class="text-center text-muted-foreground py-12">
      <FileArchive class="mx-auto mb-3 h-10 w-10" />
      <p v-if="search.trim()">No packages match “{{ search.trim() }}”.</p>
      <p v-else>No packages yet. Create your first one above.</p>
    </div>

    <template v-else>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink
          v-for="pkg in packages"
          :key="pkg.id"
          :to="{ name: 'package', params: { id: pkg.id } }"
          class="min-w-0"
        >
          <Card class="h-full transition-colors hover:border-primary">
            <CardHeader>
              <CardTitle class="flex items-center justify-between gap-2 text-lg">
                <span class="truncate">{{ pkg.name }}</span>
                <Share2 class="h-4 w-4 shrink-0 text-muted-foreground" />
              </CardTitle>
              <CardDescription>
                {{ pkg.file_count }} file(s)
              </CardDescription>
            </CardHeader>
            <CardContent v-if="pkg.description">
              <p class="text-sm text-muted-foreground line-clamp-2">{{ pkg.description }}</p>
            </CardContent>
          </Card>
        </RouterLink>
      </div>

      <div
        v-if="total > pageSize"
        class="flex items-center justify-between text-sm text-muted-foreground"
      >
        <span>{{ total }} package{{ total === 1 ? "" : "s" }}</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="offset === 0" @click="prev">
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="offset + pageSize >= total"
            @click="next"
          >
            Next
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
