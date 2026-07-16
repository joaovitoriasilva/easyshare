<script setup lang="ts">
import { computed, type Component } from "vue";
import { cva } from "class-variance-authority";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-vue-next";
import { cn } from "@/lib/utils";
import type { Toast, ToastVariant } from "@/stores/toast";

const props = defineProps<{ toast: Toast }>();
const emit = defineEmits<{
  (event: "close"): void;
  (event: "pause"): void;
  (event: "resume"): void;
}>();

const toastVariants = cva(
  "pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-md border bg-card p-4 pr-10 text-card-foreground shadow-lg",
  {
    variants: {
      variant: {
        success: "border-green-500/40",
        error: "border-destructive/50",
        warning: "border-amber-500/40",
        info: "border-primary/40",
      },
    },
    defaultVariants: { variant: "info" },
  },
);

const icons: Record<ToastVariant, Component> = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
};

const iconClass: Record<ToastVariant, string> = {
  success: "text-green-600 dark:text-green-500",
  error: "text-destructive",
  warning: "text-amber-500",
  info: "text-primary",
};

const icon = computed<Component>(() => icons[props.toast.variant]);
const role = computed(() =>
  props.toast.variant === "error" || props.toast.variant === "warning"
    ? "alert"
    : "status",
);
</script>

<template>
  <div
    :class="cn(toastVariants({ variant: props.toast.variant }))"
    :role="role"
    @mouseenter="emit('pause')"
    @mouseleave="emit('resume')"
  >
    <component
      :is="icon"
      class="mt-0.5 h-5 w-5 shrink-0"
      :class="iconClass[props.toast.variant]"
    />
    <div class="flex-1 space-y-1">
      <p class="text-sm font-medium leading-none">{{ props.toast.title }}</p>
      <p v-if="props.toast.description" class="text-sm text-muted-foreground">
        {{ props.toast.description }}
      </p>
    </div>
    <button
      type="button"
      class="absolute right-2 top-2 rounded-md p-1 text-muted-foreground/70 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label="Dismiss notification"
      @click="emit('close')"
    >
      <X class="h-4 w-4" />
    </button>
  </div>
</template>
