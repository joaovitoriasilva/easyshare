<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Download, Lock, MailCheck, Package2 } from "lucide-vue-next";
import { publicApi } from "@/api";
import { ApiError } from "@/api/client";
import type { PublicShare } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { downloadUrl } from "@/lib/download";
import { fileIcon } from "@/lib/fileIcon";
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
                  <Input id="email" v-model="email" type="email" placeholder="you@example.com" />
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
