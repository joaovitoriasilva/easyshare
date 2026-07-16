<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { FileArchive, Plus, Share2 } from "lucide-vue-next";
import { packagesApi } from "@/api";
import { ApiError } from "@/api/client";
import type { Package } from "@/api/types";
import { useToasts } from "@/composables/useToasts";
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
} from "@/components/ui";

const toast = useToasts();

const packages = ref<Package[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const showForm = ref(false);
const name = ref("");
const description = ref("");
const creating = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  try {
    packages.value = await packagesApi.list();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load packages";
  } finally {
    loading.value = false;
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
    packages.value.unshift(created);
    name.value = "";
    description.value = "";
    showForm.value = false;
    toast.success(`Created "${created.name}"`);
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to create package");
  } finally {
    creating.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Your packages</h1>
        <p class="text-muted-foreground">Create packages and share them securely</p>
      </div>
      <Button @click="showForm = !showForm">
        <Plus class="h-4 w-4" /> New package
      </Button>
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
    <p v-if="loading" class="text-muted-foreground">Loading...</p>

    <div v-else-if="packages.length === 0" class="text-center text-muted-foreground py-12">
      <FileArchive class="mx-auto mb-3 h-10 w-10" />
      <p>No packages yet. Create your first one above.</p>
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <RouterLink
        v-for="pkg in packages"
        :key="pkg.id"
        :to="{ name: 'package', params: { id: pkg.id } }"
      >
        <Card class="h-full transition-colors hover:border-primary">
          <CardHeader>
            <CardTitle class="flex items-center justify-between text-lg">
              {{ pkg.name }}
              <Share2 class="h-4 w-4 text-muted-foreground" />
            </CardTitle>
            <CardDescription>
              {{ pkg.files.length }} file(s)
            </CardDescription>
          </CardHeader>
          <CardContent v-if="pkg.description">
            <p class="text-sm text-muted-foreground line-clamp-2">{{ pkg.description }}</p>
          </CardContent>
        </Card>
      </RouterLink>
    </div>
  </div>
</template>
