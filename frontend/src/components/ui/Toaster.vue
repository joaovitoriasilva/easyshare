<script setup lang="ts">
import { useToastStore } from "@/stores/toast";
import Toast from "./Toast.vue";

const toast = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div
      class="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
      role="region"
      aria-label="Notifications"
    >
      <TransitionGroup name="toast">
        <Toast
          v-for="item in toast.toasts"
          :key="item.id"
          :toast="item"
          class="w-full sm:max-w-sm"
          @close="toast.dismiss(item.id)"
          @pause="toast.pause(item.id)"
          @resume="toast.resume(item.id)"
        />
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateY(0.75rem);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(1rem);
}

.toast-move {
  transition: transform 0.25s ease;
}
</style>
