<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ApiError } from "@/api/client";
import { useToasts } from "@/composables/useToasts";
import { isValidEmail } from "@/lib/validation";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Tooltip,
} from "@/components/ui";

const auth = useAuthStore();
const router = useRouter();
const toast = useToasts();

const email = ref("");
const username = ref("");
const password = ref("");
const error = ref<string | null>(null);
const loading = ref(false);

const emailValid = computed(() => isValidEmail(email.value));
const showEmailError = computed(() => email.value.length > 0 && !emailValid.value);

// Mirror the backend constraints so the button only enables for a submittable form.
const usernameValid = computed(() => /^[A-Za-z0-9_.-]{3,64}$/.test(username.value));
const passwordValid = computed(
  () => password.value.length >= 8 && password.value.length <= 128,
);
const canSubmit = computed(
  () => emailValid.value && usernameValid.value && passwordValid.value,
);

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
        <CardDescription>Start creating and sharing packages</CardDescription>
      </CardHeader>
      <form @submit.prevent="submit">
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="email">Email</Label>
            <Tooltip content="Enter a valid email address" :open="showEmailError">
              <Input id="email" v-model="email" type="email" placeholder="joao@example.com" />
            </Tooltip>
          </div>
          <div class="space-y-2">
            <Label for="username">Username</Label>
            <Input id="username" v-model="username" placeholder="joao" />
            <p class="text-xs text-muted-foreground">
              3+ characters: letters, numbers, dot, underscore or hyphen.
            </p>
          </div>
          <div class="space-y-2">
            <Label for="password">Password</Label>
            <Input id="password" v-model="password" type="password" placeholder="Password" />
            <p class="text-xs text-muted-foreground">At least 8 characters.</p>
          </div>
          <Alert v-if="error" kind="error">{{ error }}</Alert>
        </CardContent>
        <CardFooter class="flex flex-col gap-3">
          <Button type="submit" class="w-full" :disabled="loading || !canSubmit">
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
