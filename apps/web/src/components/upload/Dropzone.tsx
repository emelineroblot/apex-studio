"use client";

import { useId, useRef, useState } from "react";
import clsx from "clsx";

export function Dropzone({
  onFiles,
  disabled,
  label = "Déposez vos photos ici",
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  label?: string;
}) {
  const inputId = useId();
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/") || f.size > 0);
    if (files.length > 0) onFiles(files);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (!disabled) handleFiles(e.dataTransfer.files);
      }}
      className={clsx(
        "flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
        dragOver ? "border-accent-500 bg-accent-50" : "border-ink-200 bg-white",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <p className="text-sm font-medium text-ink-800">{label}</p>
      <p className="text-xs text-ink-500">JPEG, PNG — plusieurs centaines de fichiers à la fois.</p>
      <label
        htmlFor={inputId}
        className="mt-2 cursor-pointer rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 focus-within:outline-2 focus-within:outline-accent-600 focus-within:outline-offset-2"
      >
        Choisir des fichiers
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          accept="image/*"
          disabled={disabled}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
          className="sr-only"
        />
      </label>
    </div>
  );
}
