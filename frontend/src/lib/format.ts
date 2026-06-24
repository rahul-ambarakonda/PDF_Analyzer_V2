import type { FolderFile } from '../types';

export function toFolderFiles(files: File[]): FolderFile[] {
  return files.map((file) => ({
    file,
    name: file.name,
    path: file.webkitRelativePath || file.name,
    size: file.size,
  }));
}

export function folderLabel(files: FolderFile[]): string {
  if (files.length === 0) return '';
  const firstPath = files[0].path;
  const parts = firstPath.split('/');
  if (parts.length > 1) {
    return parts[0];
  }
  return 'Selected Folder';
}

export function formatTimestamp(date: Date): string {
  return date.toLocaleString();
}
