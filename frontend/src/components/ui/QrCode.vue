<script setup lang="ts">
import QrcodeVue from "qrcode.vue";

/**
 * Renders a QR code for a value (typically a share link). The code is always
 * drawn dark-on-white inside a white plate so it stays scannable regardless of
 * the app theme, and is exposed to assistive tech as a single labelled image.
 */
withDefaults(
  defineProps<{
    value: string;
    size?: number;
    label?: string;
  }>(),
  { size: 148, label: "QR code" },
);
</script>

<template>
  <div
    class="inline-flex items-center justify-center rounded-md bg-white p-3 shadow-sm ring-1 ring-black/5"
    role="img"
    :aria-label="label"
  >
    <QrcodeVue
      :value="value"
      :size="size"
      level="M"
      render-as="svg"
      foreground="#000000"
      background="#ffffff"
    />
  </div>
</template>
