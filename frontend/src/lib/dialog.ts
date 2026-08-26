export const dialogOverlayClass = "fixed inset-0 z-[90] bg-black/60";

const responsiveDialogContentBaseClass =
  "fixed inset-x-0 bottom-0 z-[100] max-h-[90dvh] w-full overflow-y-auto rounded-t-lg border border-b-0 bg-card p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] text-card-foreground shadow-xl focus:outline-hidden sm:left-1/2 sm:right-auto sm:top-1/2 sm:bottom-auto sm:max-h-[calc(100dvh-2rem)] sm:w-[calc(100%-2rem)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-lg sm:border-b sm:p-6 sm:pb-6";

export function responsiveDialogContentClass(size: "md" | "lg" = "md"): string {
  return `${responsiveDialogContentBaseClass} ${size === "lg" ? "sm:max-w-lg" : "sm:max-w-md"}`;
}