<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
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
const route = useRoute();
const toast = useToastStore();

const identifier = ref("");
const password = ref("");
const error = ref<string | null>(null);
const loading = ref(false);

async function submit(): Promise<void> {
  error.value = null;
  loading.value = true;
  try {
    await auth.login(identifier.value, password.value);
    toast.success("Signed in");
    const redirect = (route.query.redirect as string) || "/dashboard";
    router.push(redirect);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Login failed";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-md">
    <Card>
      <CardHeader>
        <CardTitle>Welcome back</CardTitle>
        <CardDescription>Sign in to manage your shared packages.</CardDescription>
      </CardHeader>
      <form @submit.prevent="submit">
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="identifier">Username or email</Label>
            <Input id="identifier" v-model="identifier" placeholder="alice" />
          </div>
          <div class="space-y-2">
            <Label for="password">Password</Label>
            <Input id="password" v-model="password" type="password" />
          </div>
          <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
        </CardContent>
        <CardFooter class="flex flex-col gap-3">
          <Button type="submit" class="w-full" :disabled="loading">
            {{ loading ? "Signing in..." : "Sign in" }}
          </Button>
          <p v-if="auth.allowRegistration" class="text-sm text-muted-foreground">
            No account?
            <RouterLink to="/register" class="text-primary hover:underline">
              Create one
            </RouterLink>
          </p>
        </CardFooter>
      </form>
    </Card>
  </div>
</template>
