<script setup lang="ts">
import { computed } from "vue";
import { Monitor, Moon, Sun } from "@lucide/vue";
import { Button } from "@/components/ui";
import { useThemeStore } from "@/stores/theme";

const theme = useThemeStore();

const label = computed(() => {
  if (theme.preference === "system") {
    return `Theme: System (${theme.resolvedTheme})`;
  }
  return theme.preference === "dark" ? "Theme: Dark" : "Theme: Light";
});
</script>

<template>
  <Button
    variant="ghost"
    size="icon"
    :title="label"
    :aria-label="label"
    @click="theme.cyclePreference()"
  >
    <Monitor v-if="theme.preference === 'system'" class="h-4 w-4" />
    <Sun v-else-if="theme.preference === 'light'" class="h-4 w-4" />
    <Moon v-else class="h-4 w-4" />
  </Button>
</template>
