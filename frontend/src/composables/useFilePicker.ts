import { ref, type ComponentPublicInstance } from "vue";

type FileHandler = (files: File[]) => void | Promise<void>;

export function useFilePicker(handleFiles: FileHandler) {
  const dragging = ref(false);
  const fileInput = ref<HTMLInputElement | null>(null);
  const folderInput = ref<HTMLInputElement | null>(null);

  function setFileInput(el: Element | ComponentPublicInstance | null): void {
    fileInput.value = el instanceof HTMLInputElement ? el : null;
  }

  function setFolderInput(el: Element | ComponentPublicInstance | null): void {
    const input = el instanceof HTMLInputElement ? el : null;
    folderInput.value = input;
    if (input) {
      input.setAttribute("webkitdirectory", "");
      input.setAttribute("directory", "");
    }
  }

  function onPick(event: Event): void {
    const target = event.target as HTMLInputElement;
    const files = target.files ? Array.from(target.files) : [];
    if (files.length > 0) {
      void handleFiles(files);
    }
    target.value = "";
  }

  function onDrop(event: DragEvent): void {
    dragging.value = false;
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      void handleFiles(Array.from(files));
    }
  }

  function openFiles(): void {
    fileInput.value?.click();
  }

  function openFolder(): void {
    folderInput.value?.click();
  }

  return {
    dragging,
    setFileInput,
    setFolderInput,
    onPick,
    onDrop,
    openFiles,
    openFolder,
  };
}