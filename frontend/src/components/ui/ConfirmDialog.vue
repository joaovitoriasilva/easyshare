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
import { dialogOverlayClass, responsiveDialogContentClass } from "@/lib/dialog";

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
      <AlertDialogOverlay :class="dialogOverlayClass" />
      <AlertDialogContent
        :class="responsiveDialogContentClass()"
      >
        <AlertDialogTitle class="text-lg font-semibold">{{ state.title }}</AlertDialogTitle>
        <AlertDialogDescription class="mt-2 text-sm text-muted-foreground">
          {{ state.message }}
        </AlertDialogDescription>
        <div class="mt-6 flex justify-end gap-2">
          <Button class="h-11 sm:h-10" variant="outline" @click="cancel">
            {{ state.cancelText }}
          </Button>
          <Button
            class="h-11 sm:h-10"
            :variant="state.destructive ? 'destructive' : 'default'"
            @click="accept"
          >
            {{ state.confirmText }}
          </Button>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
