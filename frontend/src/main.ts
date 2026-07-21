import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { getToken, setUnauthorizedHandler, setRateLimitedHandler } from "./api/client";
import { useAuthStore } from "./stores/auth";
import { useThemeStore } from "./stores/theme";
import { useToasts } from "./composables/useToasts";
import "./assets/main.css";

const app = createApp(App);

// Surface otherwise-silent uncaught errors from render/handlers as a toast.
app.config.errorHandler = (error, _instance, info) => {
  console.error(error, info);
  useToasts().error("Something went wrong. Please try again.");
};

app.use(createPinia());
app.use(router);

// When an authenticated request is rejected with 401 (e.g. the token expired),
// clear the session and send the user to login with a single clear message,
// instead of surfacing a scattered per-view error.
const auth = useAuthStore();
setUnauthorizedHandler(() => {
  if (!getToken()) {
    return;
  }
  auth.logout();
  const current = router.currentRoute.value;
  if (current.name !== "login") {
    useToasts().error("Your session has expired. Please sign in again.");
    void router.push({ name: "login", query: { redirect: current.fullPath } });
  }
});

// Surface rate-limit (429) responses as one friendly, actionable toast with the
// server's Retry-After hint. Throttled so a burst of throttled requests can't
// stack duplicate toasts on top of each other.
let lastRateLimitToastAt = 0;
setRateLimitedHandler((retryAfterSeconds) => {
  const now = Date.now();
  if (now - lastRateLimitToastAt < 3000) {
    return;
  }
  lastRateLimitToastAt = now;
  const hint =
    retryAfterSeconds && retryAfterSeconds > 0
      ? ` Please try again in ${retryAfterSeconds}s.`
      : " Please slow down and try again shortly.";
  useToasts().warning(`Too many requests.${hint}`);
});

useThemeStore().init();
app.mount("#app");
