<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { adminApi } from "@/api";
import { ApiError } from "@/api/client";
import type { AdminUser, AdminUserUpdate } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useToasts } from "@/composables/useToasts";
import { useConfirm } from "@/composables/useConfirm";
import { isValidEmail } from "@/lib/validation";
import { formatBytes } from "@/lib/format";
import { Button, Input, Tooltip } from "@/components/ui";

const auth = useAuthStore();
const toast = useToasts();
const { confirm } = useConfirm();

const users = ref<AdminUser[]>([]);
const total = ref(0);
const offset = ref(0);
const loading = ref(true);
const limit = 50;

const editingId = ref<number | null>(null);
const editUsername = ref("");
const editEmail = ref("");
const editQuotaMb = ref("");
const bulkQuotaMb = ref("");

const editEmailValid = computed(() => isValidEmail(editEmail.value));
const showEditEmailError = computed(
  () => editEmail.value.length > 0 && !editEmailValid.value,
);

/** A storage-quota MB input is valid when it is a non-negative number. */
function isValidMb(raw: string): boolean {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return false;
  }
  const mb = Number(trimmed);
  return Number.isFinite(mb) && mb >= 0;
}
function mbToBytes(raw: string): number {
  return Math.round(Number(raw.trim()) * 1024 * 1024);
}

const editQuotaValid = computed(() => isValidMb(editQuotaMb.value));
const bulkQuotaValid = computed(() => isValidMb(bulkQuotaMb.value));

async function load(): Promise<void> {
  loading.value = true;
  try {
    const page = await adminApi.listUsers({ limit, offset: offset.value });
    users.value = page.items;
    total.value = page.total;
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to load users");
  } finally {
    loading.value = false;
  }
}

function isSelf(user: AdminUser): boolean {
  return auth.user?.id === user.id;
}

/** Human label for a user's quota: a size or "Unlimited" (0). */
function quotaLabel(user: AdminUser): string {
  if (user.storage_quota === 0) {
    return "Unlimited";
  }
  return formatBytes(user.storage_quota);
}

async function patch(user: AdminUser, changes: AdminUserUpdate): Promise<void> {
  try {
    const updated = await adminApi.updateUser(user.id, changes);
    const index = users.value.findIndex((u) => u.id === user.id);
    if (index !== -1) {
      users.value[index] = updated;
    }
    toast.success("User updated");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Update failed");
  }
}

function toggleAdmin(user: AdminUser): void {
  patch(user, { is_admin: !user.is_admin });
}

function toggleActive(user: AdminUser): void {
  patch(user, { is_active: !user.is_active });
}

async function deleteUser(user: AdminUser): Promise<void> {
  const confirmed = await confirm({
    title: "Delete user",
    message: `"${user.username}" and all of their packages and files will be permanently deleted.`,
    confirmText: "Delete",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  try {
    await adminApi.deleteUser(user.id);
    users.value = users.value.filter((u) => u.id !== user.id);
    total.value -= 1;
    toast.success("User deleted");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to delete user");
  }
}

function startEdit(user: AdminUser): void {
  editingId.value = user.id;
  editUsername.value = user.username;
  editEmail.value = user.email;
  editQuotaMb.value = String(Math.round(user.storage_quota / (1024 * 1024)));
}

function cancelEdit(): void {
  editingId.value = null;
}

async function saveEdit(user: AdminUser): Promise<void> {
  await patch(user, {
    username: editUsername.value,
    email: editEmail.value,
    storage_quota: mbToBytes(editQuotaMb.value),
  });
  editingId.value = null;
}

async function applyBulkQuota(): Promise<void> {
  const confirmed = await confirm({
    title: "Set quota for all users",
    message: `Every user's storage quota will be set to ${bulkQuotaMb.value.trim()} MB (0 = unlimited). This overwrites individual quotas.`,
    confirmText: "Apply to all",
    destructive: true,
  });
  if (!confirmed) {
    return;
  }
  try {
    const { updated } = await adminApi.setAllQuotas(mbToBytes(bulkQuotaMb.value));
    toast.success(`Updated ${updated} user(s)`);
    await load();
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update quotas");
  }
}

function next(): void {
  if (offset.value + limit < total.value) {
    offset.value += limit;
    load();
  }
}

function prev(): void {
  if (offset.value > 0) {
    offset.value = Math.max(0, offset.value - limit);
    load();
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-2xl font-bold">Users</h1>
      <p class="text-muted-foreground">Manage registered users and their roles</p>
    </div>

    <div
      class="flex flex-col gap-3 rounded-md border bg-card p-4 sm:flex-row sm:items-end sm:justify-between"
    >
      <div class="space-y-1">
        <p class="text-sm font-medium">Set quota for all users</p>
        <p class="text-xs text-muted-foreground">
          Applies to every user; 0 = unlimited. Overwrites individual quotas.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Input
          v-model="bulkQuotaMb"
          type="number"
          min="0"
          placeholder="MB"
          class="h-9 w-28"
        />
        <span class="text-sm text-muted-foreground">MB</span>
        <Button size="sm" :disabled="!bulkQuotaValid" @click="applyBulkQuota">
          Apply to all
        </Button>
      </div>
    </div>

    <p v-if="loading" class="text-muted-foreground">Loading...</p>
    <template v-else>
      <div class="overflow-x-auto rounded-md border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th class="p-3 font-medium">Username</th>
              <th class="p-3 font-medium">Email</th>
              <th class="p-3 font-medium">Role</th>
              <th class="p-3 font-medium">Status</th>
              <th class="p-3 font-medium">Storage</th>
              <th class="p-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id" class="border-t">
              <td class="p-3">
                <Input
                  v-if="editingId === user.id"
                  v-model="editUsername"
                  class="h-8"
                />
                <span v-else>
                  {{ user.username }}
                  <span v-if="isSelf(user)" class="ml-1 text-xs text-muted-foreground">
                    (you)
                  </span>
                </span>
              </td>
              <td class="p-3">
                <Tooltip
                  v-if="editingId === user.id"
                  content="Enter a valid email address"
                  :open="showEditEmailError"
                >
                  <Input v-model="editEmail" type="email" class="h-8" />
                </Tooltip>
                <span v-else class="text-muted-foreground">{{ user.email }}</span>
              </td>
              <td class="p-3">
                <span :class="user.is_admin ? 'font-medium text-primary' : 'text-muted-foreground'">
                  {{ user.is_admin ? "Admin" : "User" }}
                </span>
              </td>
              <td class="p-3">
                <span :class="user.is_active ? 'text-muted-foreground' : 'text-destructive'">
                  {{ user.is_active ? "Active" : "Inactive" }}
                </span>
              </td>
              <td class="p-3">
                <div v-if="editingId === user.id" class="flex items-center gap-1">
                  <Input
                    v-model="editQuotaMb"
                    type="number"
                    min="0"
                    class="h-8 w-20"
                    title="Storage quota in MB. 0 = unlimited."
                  />
                  <span class="text-xs text-muted-foreground">MB</span>
                </div>
                <span v-else class="whitespace-nowrap text-muted-foreground">
                  {{ formatBytes(user.storage_used) }} / {{ quotaLabel(user) }}
                </span>
              </td>
              <td class="p-3">
                <div class="flex justify-end gap-2">
                  <template v-if="editingId === user.id">
                    <Button size="sm" :disabled="!editEmailValid || !editQuotaValid" @click="saveEdit(user)">Save</Button>
                    <Button variant="ghost" size="sm" @click="cancelEdit">Cancel</Button>
                  </template>
                  <template v-else>
                    <Button variant="outline" size="sm" @click="startEdit(user)">
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="isSelf(user)"
                      @click="toggleAdmin(user)"
                    >
                      {{ user.is_admin ? "Revoke admin" : "Make admin" }}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="isSelf(user)"
                      @click="toggleActive(user)"
                    >
                      {{ user.is_active ? "Deactivate" : "Activate" }}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      :disabled="isSelf(user)"
                      @click="deleteUser(user)"
                    >
                      Delete
                    </Button>
                  </template>
                </div>
              </td>
            </tr>
            <tr v-if="users.length === 0">
              <td colspan="6" class="p-4 text-center text-muted-foreground">
                No users.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-between text-sm text-muted-foreground">
        <span>{{ total }} user(s)</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="offset === 0" @click="prev">
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="offset + limit >= total"
            @click="next"
          >
            Next
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
