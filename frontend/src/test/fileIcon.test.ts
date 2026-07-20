import { describe, expect, it } from "vitest";
import {
  File,
  FileArchive,
  FileImage,
  FileText,
} from "lucide-vue-next";
import { fileIcon } from "@/lib/fileIcon";

describe("fileIcon", () => {
  it("maps known extensions to a matching icon", () => {
    expect(fileIcon("photo.png")).toBe(FileImage);
    expect(fileIcon("archive.zip")).toBe(FileArchive);
    expect(fileIcon("notes.pdf")).toBe(FileText);
  });

  it("is case-insensitive", () => {
    expect(fileIcon("PHOTO.JPG")).toBe(FileImage);
  });

  it("falls back to a generic file icon for unknown or missing extensions", () => {
    expect(fileIcon("mystery.qwerty")).toBe(File);
    expect(fileIcon("no-extension")).toBe(File);
  });
});
