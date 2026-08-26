<script setup lang="ts">
import { RouterLink } from "vue-router";
import { FileQuestion } from "@lucide/vue";
import { Button, EmptyState } from "@/components/ui";
</script>

<template>
  <div class="mx-auto max-w-2xl py-8 sm:py-16">
    <EmptyState
      :icon="FileQuestion"
      :heading-level="1"
      title="Page not found"
      description="The page may have moved or the address may be incorrect."
      class="border-0"
    >
      <Button as-child>
        <RouterLink to="/">Go home</RouterLink>
      </Button>
    </EmptyState>
  </div>
</template>
