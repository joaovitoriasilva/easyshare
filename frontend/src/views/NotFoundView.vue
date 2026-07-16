<script setup lang="ts">
import { RouterLink } from "vue-router";
import { Button } from "@/components/ui";
</script>

<template>
  <div class="mx-auto max-w-md text-center py-16">
    <h1 class="text-4xl font-bold">404</h1>
    <p class="mt-2 text-muted-foreground">This page could not be found.</p>
    <RouterLink to="/" class="mt-6 inline-block">
      <Button>Go home</Button>
    </RouterLink>
  </div>
</template>
