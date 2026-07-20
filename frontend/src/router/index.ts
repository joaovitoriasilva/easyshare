import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useNavigationProgress } from "@/composables/useNavigationProgress";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/dashboard",
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("@/views/RegisterView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("@/views/DashboardView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/ProfileView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/packages/:id",
      name: "package",
      component: () => import("@/views/PackageView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/activity",
      name: "activity",
      component: () => import("@/views/ActivityView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/admin/audit",
      name: "admin-audit",
      component: () => import("@/views/AdminAuditView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "/admin/users",
      name: "admin-users",
      component: () => import("@/views/AdminUsersView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "/admin/settings",
      name: "admin-settings",
      component: () => import("@/views/AdminSettingsView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "/s/:token",
      name: "share",
      component: () => import("@/views/ShareView.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
    },
  ],
});

const progress = useNavigationProgress();

// Start the top-of-page bar as soon as a navigation begins (registered before
// the auth guard so it shows even while `auth.init()` is awaited), and finish
// it when the navigation resolves or errors.
router.beforeEach(() => {
  progress.start();
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.init();

  if (to.meta.requiresAuth && !auth.user) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.requiresAdmin && !auth.user?.is_admin) {
    return { name: "dashboard" };
  }
  if (to.name === "register" && !auth.allowRegistration) {
    return { name: "login" };
  }
  if (to.meta.guestOnly && auth.user) {
    return { name: "dashboard" };
  }
  return true;
});

router.afterEach(() => {
  progress.done();
});

router.onError(() => {
  progress.done();
});

export default router;
