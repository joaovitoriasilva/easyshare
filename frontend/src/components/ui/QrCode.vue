<script setup lang="ts">
import { ref } from "vue";
import QrcodeVue from "qrcode.vue";
import { downloadBlob } from "@/lib/download";

/**
 * Renders a QR code for a value (typically a share link). The code is always
 * drawn dark-on-white inside a white plate so it stays scannable regardless of
 * the app theme, and is exposed to assistive tech as a single labelled image.
 * `download()` (exposed to the parent) rasterises the SVG to a PNG for export.
 */
const props = withDefaults(
  defineProps<{
    value: string;
    size?: number;
    label?: string;
  }>(),
  { size: 148, label: "QR code" },
);

const root = ref<HTMLElement | null>(null);

/**
 * Export the on-screen QR code as a PNG. The visible code is an SVG (crisp and
 * theme-safe); for download it is drawn onto a white canvas at a higher
 * resolution so the saved image stays sharp when printed or scanned.
 */
async function download(filename = "qr-code.png"): Promise<void> {
  const svg = root.value?.querySelector("svg");
  if (!svg) {
    return;
  }
  const serialized = new XMLSerializer().serializeToString(svg);
  const source = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;
  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("Could not render the QR code"));
    image.src = source;
  });
  const scale = 4;
  const dimension = props.size * scale;
  const canvas = document.createElement("canvas");
  canvas.width = dimension;
  canvas.height = dimension;
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, dimension, dimension);
  context.drawImage(image, 0, 0, dimension, dimension);
  await new Promise<void>((resolve) => {
    canvas.toBlob((blob) => {
      if (blob) {
        downloadBlob(blob, filename);
      }
      resolve();
    }, "image/png");
  });
}

defineExpose({ download });
</script>

<template>
  <div
    ref="root"
    class="inline-flex items-center justify-center rounded-md bg-white p-3 shadow-xs ring-1 ring-black/5"
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
