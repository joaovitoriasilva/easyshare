<script setup lang="ts">
import {
  TooltipArrow,
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipRoot,
  TooltipTrigger,
} from "reka-ui";

defineProps<{ content: string; open?: boolean }>();
</script>

<template>
  <TooltipProvider :delay-duration="150">
    <TooltipRoot :open="open">
      <TooltipTrigger as="div" class="block w-full">
        <slot />
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent
          :side-offset="6"
          class="z-50 max-w-xs rounded-md bg-destructive px-3 py-1.5 text-xs text-destructive-foreground shadow-md"
        >
          {{ content }}
          <TooltipArrow class="fill-destructive" />
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>
