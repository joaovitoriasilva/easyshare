<script setup lang="ts">
import {
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
} from "reka-ui";
import Button from "./Button.vue";
import { useConfirm } from "@/composables/useConfirm";

const { state, accept, cancel } = useConfirm();

// reka-ui only emits `update:open` for its own dismissals (escape key, pointer
// outside); accept/cancel close via the composable, so mapping every emitted
// close to `cancel` is safe and never double-resolves.
function onOpenChange(open: boolean): void {
  if (!open) {
    cancel();
  }
}
</script>

<template>
  <AlertDialogRoot :open="state.open" @update:open="onOpenChange">
    <AlertDialogPortal>
      <AlertDialogOverlay class="fixed inset-0 z-[90] bg-black/50" />
      <AlertDialogContent
        class="fixed left-1/2 top-1/2 z-[100] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-4 text-card-foreground shadow-lg focus:outline-hidden"
      >
        <AlertDialogTitle class="text-lg font-semibold">{{ state.title }}</AlertDialogTitle>
        <AlertDialogDescription class="mt-2 text-sm text-muted-foreground">
          {{ state.message }}
        </AlertDialogDescription>
        <div class="mt-6 flex justify-end gap-2">
          <Button variant="outline" @click="cancel">{{ state.cancelText }}</Button>
          <Button :variant="state.destructive ? 'destructive' : 'default'" @click="accept">
            {{ state.confirmText }}
          </Button>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
