<script setup lang="ts">
import { ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Package2, LogOut, Menu, X } from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { Button, Toaster, ConfirmDialog } from "@/components/ui";
import ThemeToggle from "@/components/ThemeToggle.vue";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const mobileOpen = ref(false);

// Close the mobile menu whenever the route changes (e.g. browser back/forward).
watch(() => route.fullPath, () => {
  mobileOpen.value = false;
});

function logout(): void {
  mobileOpen.value = false;
  auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="border-b bg-header">
      <div class="container flex h-16 items-center justify-between">
        <RouterLink
          to="/"
          class="flex items-center gap-2 font-semibold"
          @click="mobileOpen = false"
        >
          <Package2 class="h-5 w-5 text-primary" />
          <span>EasyShare</span>
        </RouterLink>

        <!-- Desktop navigation -->
        <nav class="hidden items-center gap-3 md:flex">
          <RouterLink
            v-if="auth.user"
            :to="{ name: 'activity' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Activity
          </RouterLink>
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-users' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Users
          </RouterLink>
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-audit' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Audit
          </RouterLink>
          <span v-if="auth.user" class="text-sm text-muted-foreground">{{ auth.user.username }}</span>
          <ThemeToggle />
          <Button v-if="auth.user" variant="ghost" size="sm" @click="logout">
            <LogOut class="h-4 w-4" />
            Sign out
          </Button>
        </nav>

        <!-- Mobile controls -->
        <div class="flex items-center gap-1 md:hidden">
          <ThemeToggle />
          <Button
            v-if="auth.user"
            variant="ghost"
            size="icon"
            :aria-label="mobileOpen ? 'Close menu' : 'Open menu'"
            :aria-expanded="mobileOpen"
            @click="mobileOpen = !mobileOpen"
          >
            <X v-if="mobileOpen" class="h-5 w-5" />
            <Menu v-else class="h-5 w-5" />
          </Button>
        </div>
      </div>

      <!-- Mobile navigation panel -->
      <nav v-if="auth.user && mobileOpen" class="border-t md:hidden">
        <div class="container flex flex-col gap-1 py-3">
          <RouterLink
            :to="{ name: 'activity' }"
            class="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Activity
          </RouterLink>
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-users' }"
            class="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Users
          </RouterLink>
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-audit' }"
            class="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Audit
          </RouterLink>
          <div class="mt-1 flex items-center justify-between border-t pt-2">
            <span class="px-2 text-sm text-muted-foreground">{{ auth.user.username }}</span>
            <Button variant="ghost" size="sm" @click="logout">
              <LogOut class="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </nav>
    </header>
    <main class="container py-8">
      <RouterView />
    </main>
    <Toaster />
    <ConfirmDialog />
  </div>
</template>
