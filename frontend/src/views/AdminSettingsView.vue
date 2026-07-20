<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { adminApi } from "@/api";
import { ApiError } from "@/api/client";
import type { ServiceSettings } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { useToasts } from "@/composables/useToasts";
import {
  Alert,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui";

const toast = useToasts();
const data = ref<ServiceSettings | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

function quota(bytes: number): string {
  return bytes === 0 ? "Unlimited" : formatBytes(bytes);
}

function duration(minutes: number): string {
  if (minutes % 1440 === 0) {
    const days = minutes / 1440;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

interface SettingRow {
  label: string;
  value: string;
}
interface SettingGroup {
  title: string;
  rows: SettingRow[];
}

const groups = computed<SettingGroup[]>(() => {
  const s = data.value;
  if (!s) {
    return [];
  }
  return [
    {
      title: "Core",
      rows: [
        { label: "Application name", value: s.app_name },
        { label: "Environment", value: s.environment },
        { label: "Deployment profile", value: s.deployment_profile },
        { label: "Registration", value: s.allow_registration ? "Open" : "Disabled" },
      ],
    },
    {
      title: "Authentication",
      rows: [
        { label: "JWT algorithm", value: s.algorithm },
        { label: "Access token lifetime", value: duration(s.access_token_expire_minutes) },
        {
          label: "Share access token lifetime",
          value: duration(s.share_access_token_expire_minutes),
        },
      ],
    },
    {
      title: "Database",
      rows: [
        { label: "Backend", value: s.database_backend },
        { label: "Pool size", value: String(s.db_pool_size) },
        { label: "Max overflow", value: String(s.db_max_overflow) },
        { label: "Pool timeout", value: `${s.db_pool_timeout}s` },
      ],
    },
    {
      title: "Storage",
      rows: [
        { label: "Backend", value: s.storage_backend },
        { label: "Obfuscate file names", value: yesNo(s.obfuscate_storage_names) },
        { label: "Max file size", value: formatBytes(s.max_file_size) },
        { label: "Max files per package", value: String(s.max_files_per_package) },
        { label: "Max archive size", value: formatBytes(s.max_archive_size) },
        {
          label: "Concurrent archive builds",
          value: String(s.max_concurrent_archive_builds),
        },
      ],
    },
    {
      title: "Quotas",
      rows: [
        { label: "Per-user quota", value: quota(s.storage_quota_per_user) },
        { label: "Instance-wide quota", value: quota(s.storage_quota_total) },
      ],
    },
    {
      title: "Rate limiting",
      rows: [
        { label: "Enabled", value: yesNo(s.rate_limit_enabled) },
        { label: "Backend", value: s.rate_limit_backend },
      ],
    },
    {
      title: "Email / verification",
      rows: [
        { label: "Email verification", value: yesNo(s.email_verification_enabled) },
        { label: "SMTP STARTTLS", value: yesNo(s.smtp_use_tls) },
        { label: "SMTP timeout", value: `${s.smtp_timeout}s` },
        {
          label: "Verification code lifetime",
          value: duration(s.share_verification_code_ttl_minutes),
        },
        {
          label: "Max verification attempts",
          value: String(s.share_verification_max_attempts),
        },
      ],
    },
    {
      title: "Logging & audit",
      rows: [
        { label: "Log level", value: s.log_level },
        { label: "Log format", value: s.log_format },
        {
          label: "Audit retention",
          value: s.audit_retention_days > 0 ? `${s.audit_retention_days} days` : "Indefinite",
        },
        { label: "Audit prune interval", value: `${s.audit_prune_interval_hours}h` },
      ],
    },
    {
      title: "CORS",
      rows: [
        {
          label: "Allowed origins",
          value: s.cors_origins.length ? s.cors_origins.join(", ") : "None",
        },
      ],
    },
  ];
});

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    data.value = await adminApi.settings();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load settings";
    toast.error(error.value);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-2xl font-bold">Settings</h1>
      <p class="text-muted-foreground">
        Read-only view of the service configuration. Secrets such as the signing
        key and connection credentials are never exposed.
      </p>
    </div>

    <Alert v-if="error" kind="error">{{ error }}</Alert>

    <div v-if="loading" class="grid gap-4 md:grid-cols-2">
      <Skeleton v-for="n in 6" :key="n" class="h-48 w-full rounded-lg" />
    </div>

    <div v-else-if="data" class="grid gap-4 md:grid-cols-2 md:items-start">
      <Card v-for="group in groups" :key="group.title">
        <CardHeader>
          <CardTitle class="text-lg">{{ group.title }}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl class="divide-y text-sm">
            <div
              v-for="row in group.rows"
              :key="row.label"
              class="flex items-start justify-between gap-4 py-2 first:pt-0 last:pb-0"
            >
              <dt class="shrink-0 text-muted-foreground">{{ row.label }}</dt>
              <dd class="break-all text-right font-medium">{{ row.value }}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
