import { nextTick } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useNavigationProgress } from "@/composables/useNavigationProgress";
import { setDocumentTitle } from "@/composables/useDocumentTitle";

declare module "vue-router" {
  interface RouteMeta {
    /** Static tab title for the route; dynamic views refine it after loading. */
    title?: string;
    requiresAuth?: boolean;
    requiresAdmin?: boolean;
    guestOnly?: boolean;
  }
}

const router = createRouter({
  history: createWebHistory(),
  // Start each navigation at the top of the page (a hash target wins), matching
  // a full page load and keeping long lists from opening scrolled midway.
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      redirect: "/dashboard",
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { guestOnly: true, title: "Sign in" },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("@/views/RegisterView.vue"),
      meta: { guestOnly: true, title: "Create account" },
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("@/views/DashboardView.vue"),
      meta: { requiresAuth: true, title: "Your packages" },
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/ProfileView.vue"),
      meta: { requiresAuth: true, title: "Profile" },
    },
    {
      path: "/packages/:id",
      name: "package",
      component: () => import("@/views/PackageView.vue"),
      meta: { requiresAuth: true, title: "Package" },
    },
    {
      path: "/activity",
      name: "activity",
      component: () => import("@/views/ActivityView.vue"),
      meta: { requiresAuth: true, title: "Activity" },
    },
    {
      path: "/admin/audit",
      name: "admin-audit",
      component: () => import("@/views/AdminAuditView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true, title: "Audit log" },
    },
    {
      path: "/admin/users",
      name: "admin-users",
      component: () => import("@/views/AdminUsersView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true, title: "Users" },
    },
    {
      path: "/admin/settings",
      name: "admin-settings",
      component: () => import("@/views/AdminSettingsView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true, title: "Settings" },
    },
    {
      path: "/s/:token",
      name: "share",
      component: () => import("@/views/ShareView.vue"),
      meta: { title: "Shared files" },
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
      meta: { title: "Page not found" },
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

router.afterEach((to, from, failure) => {
  progress.done();
  if (failure) {
    return;
  }
  // Set a title from the route's static label; dynamic views (a package, a
  // shared link) refine it once their data loads. Skip it for a redirect entry
  // (no component of its own).
  if (to.matched.length > 0) {
    setDocumentTitle(to.meta.title);
  }
  // Move keyboard focus to the main landmark on navigation so assistive tech
  // and keyboard users land on the new page's content rather than staying on a
  // now-removed element. Skipped on the very first load, where the browser's
  // natural top-of-document focus is preferable. `preventScroll` leaves the
  // scroll reset to `scrollBehavior`.
  if (from.matched.length > 0) {
    void nextTick(() => {
      document.getElementById("main-content")?.focus({ preventScroll: true });
    });
  }
});

router.onError(() => {
  progress.done();
});

export default router;
