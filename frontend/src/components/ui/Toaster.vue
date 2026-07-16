<script setup lang="ts">
import { X } from "lucide-vue-next";
import { useToasts } from "@/composables/useToasts";
import { severityClasses, severityIcons } from "@/lib/severity";

const { toasts, dismiss } = useToasts();
</script>

<template>
  <Teleport to="body">
    <TransitionGroup
      tag="div"
      class="pointer-events-none fixed inset-x-0 top-20 z-[100] flex flex-col items-center gap-2 px-4"
      enter-active-class="transition-opacity duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-300 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
      move-class="transition-transform duration-300 ease-out"
    >
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-md border px-3 py-2 text-sm shadow-lg backdrop-blur-sm"
        :class="severityClasses[toast.kind]"
        role="status"
        aria-live="polite"
      >
        <component :is="severityIcons[toast.kind]" class="mt-0.5 h-4 w-4 shrink-0" />
        <span class="flex-1">{{ toast.message }}</span>
        <button
          type="button"
          class="inline-flex size-5 shrink-0 items-center justify-center rounded-md opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Dismiss notification"
          @click="dismiss(toast.id)"
        >
          <X class="size-3.5" />
        </button>
      </div>
    </TransitionGroup>
  </Teleport>
</template>
