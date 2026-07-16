import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

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
      path: "/packages/:id",
      name: "package",
      component: () => import("@/views/PackageView.vue"),
      meta: { requiresAuth: true },
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

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.init();

  if (to.meta.requiresAuth && !auth.user) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "register" && !auth.allowRegistration) {
    return { name: "login" };
  }
  if (to.meta.guestOnly && auth.user) {
    return { name: "dashboard" };
  }
  return true;
});

export default router;
