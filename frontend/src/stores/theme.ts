import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "easyshare-theme";

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStoredPreference(): ThemePreference {
  if (typeof window === "undefined") {
    return "system";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") {
    return stored;
  }
  return "system";
}

export const useThemeStore = defineStore("theme", () => {
  const preference = ref<ThemePreference>(readStoredPreference());
  const systemTheme = ref<ResolvedTheme>(getSystemTheme());

  const resolvedTheme = computed<ResolvedTheme>(() =>
    preference.value === "system" ? systemTheme.value : preference.value,
  );

  function applyToDocument(): void {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.classList.toggle("dark", resolvedTheme.value === "dark");
  }

  function setPreference(next: ThemePreference): void {
    preference.value = next;
    if (typeof window !== "undefined") {
      if (next === "system") {
        window.localStorage.removeItem(STORAGE_KEY);
      } else {
        window.localStorage.setItem(STORAGE_KEY, next);
      }
    }
    applyToDocument();
  }

  function cyclePreference(): void {
    const order: ThemePreference[] = ["system", "light", "dark"];
    const next = order[(order.indexOf(preference.value) + 1) % order.length];
    setPreference(next);
  }

  function init(): void {
    applyToDocument();
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", (event) => {
      systemTheme.value = event.matches ? "dark" : "light";
      if (preference.value === "system") {
        applyToDocument();
      }
    });
  }

  return { preference, resolvedTheme, setPreference, cyclePreference, init };
});
