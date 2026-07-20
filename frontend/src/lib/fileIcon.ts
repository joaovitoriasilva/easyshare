/**
 * Map a filename to a representative lucide icon component based on its
 * extension, so file lists get a recognisable glyph instead of a generic one.
 * Unknown extensions fall back to a plain file icon.
 */
import {
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
} from "lucide-vue-next";

// All lucide icons share the same component shape; derive the type from one so
// we don't depend on an internal exported type name.
type IconComponent = typeof File;

const EXTENSION_ICONS: Record<string, IconComponent> = {
  // Images
  png: FileImage,
  jpg: FileImage,
  jpeg: FileImage,
  gif: FileImage,
  webp: FileImage,
  svg: FileImage,
  bmp: FileImage,
  ico: FileImage,
  heic: FileImage,
  avif: FileImage,
  // Archives
  zip: FileArchive,
  tar: FileArchive,
  gz: FileArchive,
  tgz: FileArchive,
  rar: FileArchive,
  "7z": FileArchive,
  bz2: FileArchive,
  xz: FileArchive,
  // Audio
  mp3: FileAudio,
  wav: FileAudio,
  flac: FileAudio,
  ogg: FileAudio,
  m4a: FileAudio,
  aac: FileAudio,
  // Video
  mp4: FileVideo,
  mov: FileVideo,
  avi: FileVideo,
  mkv: FileVideo,
  webm: FileVideo,
  wmv: FileVideo,
  // Documents
  pdf: FileText,
  doc: FileText,
  docx: FileText,
  txt: FileText,
  rtf: FileText,
  md: FileText,
  odt: FileText,
  // Spreadsheets
  csv: FileSpreadsheet,
  xls: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  ods: FileSpreadsheet,
  // Code
  js: FileCode,
  ts: FileCode,
  tsx: FileCode,
  jsx: FileCode,
  json: FileCode,
  html: FileCode,
  css: FileCode,
  py: FileCode,
  java: FileCode,
  c: FileCode,
  cpp: FileCode,
  go: FileCode,
  rs: FileCode,
  rb: FileCode,
  php: FileCode,
  sh: FileCode,
  yml: FileCode,
  yaml: FileCode,
  xml: FileCode,
  sql: FileCode,
};

export function fileIcon(filename: string): IconComponent {
  const dot = filename.lastIndexOf(".");
  const ext = dot >= 0 ? filename.slice(dot + 1).toLowerCase() : "";
  return EXTENSION_ICONS[ext] ?? File;
}
