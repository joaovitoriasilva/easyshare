<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { adminApi } from "@/api";
import { ApiError } from "@/api/client";
import type { AdminUserUpdate, User } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useToasts } from "@/composables/useToasts";
import { isValidEmail } from "@/lib/validation";
import { Button, Input, Tooltip } from "@/components/ui";

const auth = useAuthStore();
const toast = useToasts();

const users = ref<User[]>([]);
const total = ref(0);
const offset = ref(0);
const loading = ref(true);
const limit = 50;

const editingId = ref<number | null>(null);
const editUsername = ref("");
const editEmail = ref("");

const editEmailValid = computed(() => isValidEmail(editEmail.value));
const showEditEmailError = computed(
  () => editEmail.value.length > 0 && !editEmailValid.value,
);

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

function isSelf(user: User): boolean {
  return auth.user?.id === user.id;
}

async function patch(user: User, changes: AdminUserUpdate): Promise<void> {
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

function toggleAdmin(user: User): void {
  patch(user, { is_admin: !user.is_admin });
}

function toggleActive(user: User): void {
  patch(user, { is_active: !user.is_active });
}

function startEdit(user: User): void {
  editingId.value = user.id;
  editUsername.value = user.username;
  editEmail.value = user.email;
}

function cancelEdit(): void {
  editingId.value = null;
}

async function saveEdit(user: User): Promise<void> {
  await patch(user, { username: editUsername.value, email: editEmail.value });
  editingId.value = null;
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
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold">Users</h1>
      <p class="text-muted-foreground">Manage registered users and their roles.</p>
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
                <div class="flex justify-end gap-2">
                  <template v-if="editingId === user.id">
                    <Button size="sm" :disabled="!editEmailValid" @click="saveEdit(user)">Save</Button>
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
                  </template>
                </div>
              </td>
            </tr>
            <tr v-if="users.length === 0">
              <td colspan="5" class="p-6 text-center text-muted-foreground">
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
