<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Calendar, HardDrive, Mail, Shield, User as UserIcon } from "@lucide/vue";
import { authApi } from "@/api";
import { ApiError } from "@/api/client";
import type { StorageUsage } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";
import { useToasts } from "@/composables/useToasts";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  PasswordInput,
} from "@/components/ui";

const auth = useAuthStore();
const toast = useToasts();
const usage = ref<StorageUsage | null>(null);

const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const savingPassword = ref(false);
const passwordError = ref<string | null>(null);

const newPasswordValid = computed(
  () => newPassword.value.length >= 8 && newPassword.value.length <= 128,
);
const newPasswordInvalid = computed(
  () => newPassword.value.length > 0 && !newPasswordValid.value,
);
const passwordsMatch = computed(() => newPassword.value === confirmPassword.value);
const showPasswordMismatch = computed(
  () => confirmPassword.value.length > 0 && !passwordsMatch.value,
);
const canSubmitPassword = computed(
  () =>
    currentPassword.value.length > 0 &&
    newPasswordValid.value &&
    passwordsMatch.value,
);

const memberSince = computed(() => {
  const created = auth.user?.created_at;
  return created
    ? new Date(created).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "";
});

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

async function loadUsage(): Promise<void> {
  try {
    usage.value = await authApi.usage();
  } catch {
    usage.value = null;
  }
}

async function submitPassword(): Promise<void> {
  passwordError.value = null;
  if (!newPasswordValid.value) {
    passwordError.value = "New password must be at least 8 characters.";
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = "New passwords do not match.";
    return;
  }
  savingPassword.value = true;
  try {
    await authApi.changePassword(currentPassword.value, newPassword.value);
    currentPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    toast.success("Password changed");
  } catch (err) {
    passwordError.value =
      err instanceof ApiError ? err.message : "Failed to change password";
  } finally {
    savingPassword.value = false;
  }
}

onMounted(loadUsage);
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4">
    <div>
      <h1 class="text-2xl font-bold">Profile</h1>
      <p class="text-muted-foreground">Your account details</p>
    </div>

    <Card v-if="auth.user">
      <CardHeader>
        <CardTitle>Account</CardTitle>
        <CardDescription>Information associated with your account.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl class="divide-y text-sm">
          <div class="flex items-start justify-between gap-4 py-3 first:pt-0">
            <dt class="flex items-center gap-2 text-muted-foreground">
              <UserIcon class="h-4 w-4" /> Username
            </dt>
            <dd class="break-all text-right font-medium">{{ auth.user.username }}</dd>
          </div>
          <div class="flex items-start justify-between gap-4 py-3">
            <dt class="flex items-center gap-2 text-muted-foreground">
              <Mail class="h-4 w-4" /> Email
            </dt>
            <dd class="break-all text-right font-medium">{{ auth.user.email }}</dd>
          </div>
          <div class="flex items-start justify-between gap-4 py-3">
            <dt class="flex items-center gap-2 text-muted-foreground">
              <Shield class="h-4 w-4" /> Role
            </dt>
            <dd class="text-right font-medium">
              {{ auth.user.is_admin ? "Administrator" : "User" }}
            </dd>
          </div>
          <div class="flex items-start justify-between gap-4 py-3 last:pb-0">
            <dt class="flex items-center gap-2 text-muted-foreground">
              <Calendar class="h-4 w-4" /> Member since
            </dt>
            <dd class="text-right font-medium">{{ memberSince }}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>

    <Card v-if="usage">
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <HardDrive class="h-5 w-5 text-primary" /> Storage
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-2">
        <div class="flex items-center justify-between gap-2 text-sm">
          <span class="text-muted-foreground">Used</span>
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

    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>Update the password you use to sign in.</CardDescription>
      </CardHeader>
      <form @submit.prevent="submitPassword">
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="current-password">Current password</Label>
            <PasswordInput
              id="current-password"
              v-model="currentPassword"
              placeholder="Current password"
            />
          </div>
          <div class="space-y-2">
            <Label for="new-password">New password</Label>
            <PasswordInput
              id="new-password"
              v-model="newPassword"
              placeholder="New password"
            />
            <p
              class="text-xs"
              :class="newPasswordInvalid ? 'text-destructive' : 'text-muted-foreground'"
            >
              {{
                newPasswordInvalid
                  ? "Password must be between 8 and 128 characters."
                  : "At least 8 characters."
              }}
            </p>
          </div>
          <div class="space-y-2">
            <Label for="confirm-password">Confirm new password</Label>
            <PasswordInput
              id="confirm-password"
              v-model="confirmPassword"
              placeholder="Confirm new password"
            />
            <p v-if="showPasswordMismatch" class="text-xs text-destructive">
              Passwords do not match.
            </p>
          </div>
          <Alert v-if="passwordError" kind="error">{{ passwordError }}</Alert>
          <Button type="submit" :disabled="!canSubmitPassword || savingPassword">
            {{ savingPassword ? "Saving..." : "Change password" }}
          </Button>
        </CardContent>
      </form>
    </Card>
  </div>
</template>
