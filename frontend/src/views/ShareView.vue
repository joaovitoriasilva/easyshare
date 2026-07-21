<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Copy, Download, Lock, MailCheck, Package2, QrCode as QrCodeIcon, RotateCw, Share2, X } from "@lucide/vue";
import { publicApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PublicShare } from "@/api/types";
import { formatBytes, formatDuration, formatRate } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { copyText, shareOrCopy } from "@/lib/clipboard";
import { fileIcon } from "@/lib/fileIcon";
import { isValidEmail } from "@/lib/validation";
import { useToasts } from "@/composables/useToasts";
import { useArchiveDownload } from "@/composables/useArchiveDownload";
import { setDocumentTitle } from "@/composables/useDocumentTitle";
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
const token = String(route.params.token);
const toast = useToasts();

const share = ref<PublicShare | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const email = ref("");
const unlocked = ref(false);
const selected = ref<Set<number>>(new Set());

// Restricted shares with email verification: after /access emails a code, the
// recipient confirms it here before the files are revealed.
const awaitingCode = ref(false);
const code = ref("");
const codeValid = computed(() => code.value.trim().length >= 4);

// Cooldown (seconds) before another code can be requested, so a recipient can't
// hammer the resend button (the endpoint is also rate-limited server-side).
const RESEND_COOLDOWN_SECONDS = 60;
const resendIn = ref(0);
let resendTimer: ReturnType<typeof setInterval> | undefined;

function startResendCooldown(): void {
  resendIn.value = RESEND_COOLDOWN_SECONDS;
  if (resendTimer) {
    clearInterval(resendTimer);
  }
  resendTimer = setInterval(() => {
    resendIn.value -= 1;
    if (resendIn.value <= 0 && resendTimer) {
      clearInterval(resendTimer);
      resendTimer = undefined;
    }
  }, 1000);
}

onUnmounted(() => {
  if (resendTimer) {
    clearInterval(resendTimer);
  }
});

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

// Archive (zip) download with an in-app progress read-out; falls back to a
// native browser download for archives too large to stream in memory.
const {
  downloading: archiving,
  percent: archivePercent,
  indeterminate: archiveIndeterminate,
  bytesPerSecond: archiveRate,
  etaSeconds: archiveEta,
  start: startArchive,
  cancel: cancelArchive,
} = useArchiveDownload();

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    share.value = await publicApi.view(token);
    unlocked.value = !share.value.requires_email;
    setDocumentTitle(
      share.value.package_name,
      share.value.package_description ?? undefined,
    );
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Share not found";
    setDocumentTitle("Share unavailable");
  } finally {
    loading.value = false;
  }
}

// Re-share affordances: let a recipient copy this share link, use the OS share
// sheet, or reveal a QR code to open it on another device.
const shareUrl = computed(() => `${window.location.origin}/s/${token}`);
const showQr = ref(false);
const qr = ref<InstanceType<typeof QrCode> | null>(null);

async function copyLink(): Promise<void> {
  const copied = await copyText(shareUrl.value);
  if (copied) {
    toast.success("Link copied to clipboard");
  } else {
    toast.error("Couldn't copy the link");
  }
}

async function nativeShare(): Promise<void> {
  const result = await shareOrCopy({
    url: shareUrl.value,
    title: share.value?.package_name,
    text: share.value ? `Files shared with you: ${share.value.package_name}` : undefined,
  });
  if (result === "copied") {
    toast.success("Link copied to clipboard");
  } else if (result === "failed") {
    toast.error("Couldn't share the link");
  }
}

async function downloadQr(): Promise<void> {
  const base = share.value?.package_name?.trim() || "share";
  try {
    await qr.value?.download(`${base}-qr.png`);
  } catch {
    toast.error("Couldn't export the QR code");
  }
}

async function unlock(): Promise<void> {
  error.value = null;
  try {
    const result = await publicApi.access(token, email.value);
    share.value = result;
    if (result.verification_required) {
      awaitingCode.value = true;
      code.value = "";
      startResendCooldown();
      toast.info("We emailed you a verification code.");
      return;
    }
    downloadToken.value = result.download_token ?? null;
    unlocked.value = true;
    toast.success("Access granted");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Access denied";
  }
}

async function verify(): Promise<void> {
  error.value = null;
  try {
    const result = await publicApi.verify(token, email.value, code.value.trim());
    share.value = result;
    downloadToken.value = result.download_token ?? null;
    unlocked.value = true;
    awaitingCode.value = false;
    toast.success("Access granted");
  } catch (err) {
    error.value =
      err instanceof ApiError ? err.message : "Invalid or expired code";
  }
}

function resendCode(): void {
  if (resendIn.value > 0) {
    return;
  }
  code.value = "";
  void unlock();
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

async function downloadSelected(): Promise<void> {
  const chosen = hasSelection.value
    ? files.value.filter((file) => selected.value.has(file.id))
    : files.value;
  const ids = hasSelection.value ? chosen.map((file) => file.id) : [];
  const estimatedBytes = chosen.reduce((sum, file) => sum + file.size, 0);
  const filename = `${share.value?.package_name ?? "package"}.zip`;
  const outcome = await startArchive(
    publicApi.downloadUrl(token, ids, downloadToken.value),
    filename,
    estimatedBytes,
  );
  if (outcome === "completed") {
    toast.success("Download ready");
  } else if (outcome === "fell-back") {
    toast.info("Download started");
  }
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
      <CardContent>
        <Button variant="outline" size="sm" class="gap-1.5" @click="load">
          <RotateCw class="h-4 w-4" /> Try again
        </Button>
      </CardContent>
    </Card>

    <template v-else-if="share">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Package2 class="h-5 w-5 shrink-0 text-primary" />
            <span class="min-w-0 break-words">{{ share.package_name }}</span>
          </CardTitle>
          <CardDescription v-if="share.package_description">
            {{ share.package_description }}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <div v-if="!unlocked && !awaitingCode" class="space-y-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Lock class="h-4 w-4" />
              This share is restricted. Enter an authorised email to continue.
            </div>
            <form class="space-y-3" @submit.prevent="unlock">
              <div class="space-y-2">
                <Label for="email">Email</Label>
                <Tooltip content="Enter a valid email address" :open="showEmailError">
                  <Input
                    id="email"
                    v-model="email"
                    type="email"
                    placeholder="you@example.com"
                    :aria-invalid="showEmailError ? 'true' : undefined"
                  />
                </Tooltip>
              </div>
              <Alert v-if="error" kind="error">{{ error }}</Alert>
              <Button type="submit" :disabled="!emailValid">Unlock</Button>
            </form>
          </div>

          <div v-else-if="awaitingCode" class="space-y-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <MailCheck class="h-4 w-4" />
              Enter the code we emailed to
              <span class="font-medium text-foreground">{{ email }}</span>.
            </div>
            <form class="space-y-3" @submit.prevent="verify">
              <div class="space-y-2">
                <Label for="code">Verification code</Label>
                <Input
                  id="code"
                  v-model="code"
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  placeholder="123456"
                  :aria-invalid="error ? 'true' : undefined"
                />
              </div>
              <Alert v-if="error" kind="error">{{ error }}</Alert>
              <div class="flex flex-wrap items-center gap-2">
                <Button type="submit" :disabled="!codeValid">Verify</Button>
                <Button
                  type="button"
                  variant="ghost"
                  :disabled="resendIn > 0"
                  @click="resendCode"
                >
                  {{ resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code" }}
                </Button>
              </div>
            </form>
          </div>

          <div v-else class="space-y-4">
            <!-- Re-share this link: copy it, use the OS share sheet, or show a
                 QR code to open it on another device. -->
            <div class="flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="sm" class="gap-1.5" @click="nativeShare">
                <Share2 class="h-4 w-4" /> Share
              </Button>
              <Button variant="outline" size="sm" class="gap-1.5" @click="copyLink">
                <Copy class="h-4 w-4" /> Copy link
              </Button>
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
            </div>
            <div
              v-if="showQr"
              id="share-qr"
              class="flex flex-col items-center gap-3 rounded-md border p-4 text-center"
            >
              <QrCode ref="qr" :value="shareUrl" label="QR code for this share link" />
              <p class="text-xs text-muted-foreground">
                Scan to open this share on another device.
              </p>
              <Button variant="secondary" size="sm" class="gap-1.5" @click="downloadQr">
                <Download class="h-4 w-4" /> Download PNG
              </Button>
            </div>

            <div class="space-y-3">
              <div class="flex items-center justify-between gap-3">
                <label class="flex items-center gap-2 text-sm">
                  <Checkbox :model-value="allSelected" @update:model-value="toggleAll" />
                  Select all
                </label>
                <Button
                  v-if="!archiving"
                  size="sm"
                  class="shrink-0"
                  :disabled="files.length === 0"
                  @click="downloadSelected"
                >
                  <Download class="h-4 w-4" />
                  {{ hasSelection ? `Download ${selected.size} selected` : "Download all" }}
                </Button>
                <Button
                  v-else
                  variant="ghost"
                  size="sm"
                  class="shrink-0"
                  @click="cancelArchive"
                >
                  <X class="h-4 w-4" /> Cancel
                </Button>
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
                  <span v-if="archivePercent !== null" class="tabular-nums">
                    {{ archivePercent }}%
                  </span>
                </div>
                <div
                  class="h-2 overflow-hidden rounded-full bg-muted"
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
                  <component
                    :is="fileIcon(file.filename)"
                    class="h-4 w-4 shrink-0 text-muted-foreground"
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
