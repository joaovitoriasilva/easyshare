<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from "vue-router";
import { Package2, LogOut } from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { Button, Toaster } from "@/components/ui";
import ThemeToggle from "@/components/ThemeToggle.vue";

const auth = useAuthStore();
const router = useRouter();

function logout(): void {
  auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="border-b">
      <div class="container flex h-16 items-center justify-between">
        <RouterLink to="/" class="flex items-center gap-2 font-semibold">
          <Package2 class="h-5 w-5 text-primary" />
          <span>EasyShare</span>
        </RouterLink>
        <nav class="flex items-center gap-3">
          <RouterLink
            v-if="auth.user"
            :to="{ name: 'activity' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Activity
          </RouterLink>
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-audit' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Admin
          </RouterLink>
          <span v-if="auth.user" class="text-sm text-muted-foreground">{{ auth.user.username }}</span>
          <ThemeToggle />
          <Button v-if="auth.user" variant="ghost" size="sm" @click="logout">
            <LogOut class="h-4 w-4" />
            Sign out
          </Button>
        </nav>
      </div>
    </header>
    <main class="container py-8">
      <RouterView />
    </main>
    <Toaster />
  </div>
</template>
