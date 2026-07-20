<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Package2, LogOut, Menu, X } from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { Button, Toaster, ConfirmDialog, NavigationProgress } from "@/components/ui";
import ThemeToggle from "@/components/ThemeToggle.vue";
import UploadIndicator from "@/components/UploadIndicator.vue";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const mobileOpen = ref(false);

const startYear = 2026
const yearRange = computed(() => {
  const current = new Date().getFullYear()
  return current === startYear ? `${startYear}` : `${startYear} - ${current}`
})

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
  <div class="flex min-h-screen flex-col bg-background">
    <NavigationProgress />
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-[300] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:shadow focus:ring-2 focus:ring-ring"
    >
      Skip to main content
    </a>
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
        <nav aria-label="Main" class="hidden items-center gap-3 md:flex">
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
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-settings' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            Settings
          </RouterLink>
          <RouterLink
            v-if="auth.user"
            :to="{ name: 'profile' }"
            class="text-sm text-muted-foreground hover:text-foreground"
          >
            {{ auth.user.username }}
          </RouterLink>
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
            aria-controls="mobile-nav"
            @click="mobileOpen = !mobileOpen"
          >
            <X v-if="mobileOpen" class="h-5 w-5" />
            <Menu v-else class="h-5 w-5" />
          </Button>
        </div>
      </div>

      <!-- Mobile navigation panel -->
      <nav v-if="auth.user && mobileOpen" id="mobile-nav" aria-label="Mobile" class="border-t md:hidden">
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
          <RouterLink
            v-if="auth.user?.is_admin"
            :to="{ name: 'admin-settings' }"
            class="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Settings
          </RouterLink>
          <div class="mt-1 flex items-center justify-between border-t pt-2">
            <RouterLink
              :to="{ name: 'profile' }"
              class="rounded-md px-2 py-1 text-sm text-muted-foreground hover:text-foreground"
            >
              {{ auth.user.username }}
            </RouterLink>
            <Button variant="ghost" size="sm" @click="logout">
              <LogOut class="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </nav>
    </header>
    <main id="main-content" tabindex="-1" class="container flex-1 py-8 outline-none">
      <RouterView />
    </main>
    <footer class="border-t bg-header">
      <div class="container flex flex-col items-center gap-1 py-6 text-sm text-muted-foreground sm:flex-row sm:justify-between">
        <span class="flex items-center gap-2">
          <Package2 class="h-4 w-4" />
          EasyShare
        </span>
        <span>{{ yearRange }} • v0.3.0</span>
      </div>
    </footer>
    <Toaster />
    <ConfirmDialog />
    <UploadIndicator />
  </div>
</template>
