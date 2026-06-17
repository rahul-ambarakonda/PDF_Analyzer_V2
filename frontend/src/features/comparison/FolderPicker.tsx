import { useId, useRef } from 'react';

import { MAX_FILES_PER_FOLDER } from '@/lib/constants';
import { folderLabel, toFolderFiles } from '@/lib/format';
import type { FolderFile } from '@/types';

interface FolderPickerProps {
  label: string;
  count: number;
  emptyHint: string;
  promptText: string;
  onSelect: (files: FolderFile[], label: string) => void;
  onInvalid: (message: string) => void;
}

/** A folder-upload zone backed by a hidden `<input webkitdirectory>` (PDF-only). */
export function FolderPicker({
  label,
  count,
  emptyHint,
  promptText,
  onSelect,
  onInvalid,
}: FolderPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const all = Array.from(event.target.files ?? []);
    event.target.value = ''; // allow re-selecting the same folder
    if (!all.length) return;
    if (all.some((f) => !f.name.toLowerCase().endsWith('.pdf') && f.type !== 'application/pdf')) {
      onInvalid('Only PDF files are allowed in the selected folder.');
      return;
    }
    const files = toFolderFiles(all);
    if (files.length > MAX_FILES_PER_FOLDER) {
      onInvalid(
        `You can upload at most ${MAX_FILES_PER_FOLDER} PDFs per folder (this folder has ${files.length}).`,
      );
      return;
    }
    onSelect(files, folderLabel(files));
  };

  return (
    <div>
      <span className="field-label">{label}</span>
      <button
        type="button"
        className={`upload-zone ${count ? 'filled' : ''}`}
        onClick={() => inputRef.current?.click()}
        aria-describedby={inputId}
      >
        <span className="upload-icon">⬆</span>
        {count ? (
          <>
            <span className="upload-name">{count} PDF files selected</span>
            <span className="upload-sub">{count} files detected</span>
          </>
        ) : (
          <>
            <span className="upload-name">{promptText}</span>
            <span className="upload-sub">{emptyHint}</span>
          </>
        )}
      </button>
      <input
        id={inputId}
        ref={inputRef}
        className="sr-only"
        type="file"
        webkitdirectory=""
        multiple
        accept=".pdf,application/pdf"
        onChange={handleChange}
      />
    </div>
  );
}
