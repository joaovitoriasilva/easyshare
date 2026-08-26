import { describe, expect, it, vi } from "vitest";
import { useFilePicker } from "@/composables/useFilePicker";

const makeFile = (name: string): File => new File(["content"], name);

describe("useFilePicker", () => {
  it("owns file and folder inputs and opens each picker", () => {
    const picker = useFilePicker(vi.fn());
    const fileInput = document.createElement("input");
    const folderInput = document.createElement("input");
    const fileClick = vi.spyOn(fileInput, "click");
    const folderClick = vi.spyOn(folderInput, "click");

    picker.setFileInput(fileInput);
    picker.setFolderInput(folderInput);
    picker.openFiles();
    picker.openFolder();

    expect(fileClick).toHaveBeenCalledOnce();
    expect(folderClick).toHaveBeenCalledOnce();
    expect(folderInput.hasAttribute("webkitdirectory")).toBe(true);
    expect(folderInput.hasAttribute("directory")).toBe(true);
  });

  it("delivers selected files and resets the input", () => {
    const handleFiles = vi.fn();
    const picker = useFilePicker(handleFiles);
    const file = makeFile("selected.txt");
    const target = { files: [file], value: "selected" };

    picker.onPick({ target } as unknown as Event);

    expect(handleFiles).toHaveBeenCalledWith([file]);
    expect(target.value).toBe("");
  });

  it("delivers dropped files and clears drag state", () => {
    const handleFiles = vi.fn();
    const picker = useFilePicker(handleFiles);
    const file = makeFile("dropped.txt");
    picker.dragging.value = true;

    picker.onDrop({ dataTransfer: { files: [file] } } as unknown as DragEvent);

    expect(handleFiles).toHaveBeenCalledWith([file]);
    expect(picker.dragging.value).toBe(false);
  });

  it("ignores empty selections and drops", () => {
    const handleFiles = vi.fn();
    const picker = useFilePicker(handleFiles);

    picker.onPick({ target: { files: [], value: "" } } as unknown as Event);
    picker.onDrop({ dataTransfer: { files: [] } } as unknown as DragEvent);

    expect(handleFiles).not.toHaveBeenCalled();
  });
});