<script setup lang="ts">
import { ref } from "vue";
import { Eye, EyeOff } from "@lucide/vue";
import Input from "./Input.vue";

// Don't let fall-through attributes (e.g. aria-invalid) land on the wrapper
// div; forward them to the inner <input> where they belong.
defineOptions({ inheritAttrs: false });

defineProps<{
  modelValue?: string;
  id?: string;
  placeholder?: string;
}>();

defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const visible = ref(false);
</script>

<template>
  <div class="relative">
    <Input
      :id="id"
      :model-value="modelValue"
      :type="visible ? 'text' : 'password'"
      :placeholder="placeholder"
      class="pr-10"
      v-bind="$attrs"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <button
      type="button"
      :aria-label="visible ? 'Hide password' : 'Show password'"
      :aria-pressed="visible"
      class="absolute inset-y-0 right-0 flex items-center rounded-md px-3 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      @click="visible = !visible"
    >
      <EyeOff v-if="visible" class="h-4 w-4" />
      <Eye v-else class="h-4 w-4" />
    </button>
  </div>
</template>
