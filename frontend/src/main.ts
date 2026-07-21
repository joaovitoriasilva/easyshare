import { createApp } from "vue";
import { createPinia } from "pinia";
import * as Sentry from "@sentry/vue";
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

// Crash reporting via GlitchTip (Sentry-compatible). Only enabled when a DSN is
// provided at build time, so local/dev builds without the env var never phone
// home. Initialised after the app's own errorHandler above so the Sentry Vue
// integration chains to it (both the toast and the crash capture run) instead
// of replacing it.
const glitchtipDsn = import.meta.env.VITE_GLITCHTIP_DSN;
if (glitchtipDsn) {
  Sentry.init({
    app,
    dsn: glitchtipDsn,
    // Sample only a small fraction of performance transactions to limit the
    // data sent to (and stored by) GlitchTip; adjust to your needs.
    tracesSampleRate: 0.01,
    // GlitchTip does not support Sentry release-health "sessions", so drop the
    // default browser-session integration. This replaces the `autoSessionTracking:
    // false` option that older Sentry SDK versions exposed.
    integrations: (defaults) =>
      defaults.filter((integration) => integration.name !== "BrowserSession"),
  });
}

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
