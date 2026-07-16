import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
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
useThemeStore().init();
app.mount("#app");
