<script setup lang="ts">
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ApiError } from "@/api/client";
import { useToastStore } from "@/stores/toast";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@/components/ui";

const auth = useAuthStore();
const router = useRouter();
const toast = useToastStore();

const email = ref("");
const username = ref("");
const password = ref("");
const error = ref<string | null>(null);
const loading = ref(false);

async function submit(): Promise<void> {
  error.value = null;
  loading.value = true;
  try {
    await auth.register(email.value, username.value, password.value);
    toast.success("Account created");
    router.push("/dashboard");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Registration failed";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-md">
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>Start creating and sharing packages.</CardDescription>
      </CardHeader>
      <form @submit.prevent="submit">
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="email">Email</Label>
            <Input id="email" v-model="email" type="email" placeholder="you@example.com" />
          </div>
          <div class="space-y-2">
            <Label for="username">Username</Label>
            <Input id="username" v-model="username" placeholder="alice" />
          </div>
          <div class="space-y-2">
            <Label for="password">Password</Label>
            <Input id="password" v-model="password" type="password" />
            <p class="text-xs text-muted-foreground">At least 8 characters.</p>
          </div>
          <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
        </CardContent>
        <CardFooter class="flex flex-col gap-3">
          <Button type="submit" class="w-full" :disabled="loading">
            {{ loading ? "Creating..." : "Create account" }}
          </Button>
          <p class="text-sm text-muted-foreground">
            Already have an account?
            <RouterLink to="/login" class="text-primary hover:underline">Sign in</RouterLink>
          </p>
        </CardFooter>
      </form>
    </Card>
  </div>
</template>
