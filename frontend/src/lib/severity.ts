import type { Component } from "vue";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "@lucide/vue";

/** Severity vocabulary shared by inline alerts and toasts. */
export type Severity = "info" | "success" | "warning" | "error";

/**
 * Border/background/text classes for each severity. Single source of truth
 * shared by the inline Alert component and the toast host so both render
 * severities identically.
 */
export const severityClasses: Record<Severity, string> = {
  info: "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  success: "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  error: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
};

/** Leading icon for each severity. */
export const severityIcons: Record<Severity, Component> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
};
