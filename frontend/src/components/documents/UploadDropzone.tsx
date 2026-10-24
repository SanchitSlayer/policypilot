"use client";

import { CheckCircle2, FileUp, X, XCircle } from "lucide-react";
import { useRef, useState } from "react";

import { MAX_UPLOAD_MB, uploadDocument } from "@/lib/api";
import type { DocType } from "@/lib/types";

type UploadItem = {
  key: string;
  name: string;
  progress: number;
  state: "uploading" | "done" | "error";
  error?: string;
};

export function validateFile(file: File, maxMb = MAX_UPLOAD_MB): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
    return "Only PDF files are supported.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > maxMb * 1024 * 1024) return `File is larger than ${maxMb} MB.`;
  return null;
}

export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [docType, setDocType] = useState<DocType>("policy");
  const [items, setItems] = useState<UploadItem[]>([]);

  const update = (key: string, patch: Partial<UploadItem>) =>
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));

  const uploadFiles = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const key = `${file.name}-${file.size}-${crypto.randomUUID()}`;
      const invalid = validateFile(file);
      setItems((current) => [
        { key, name: file.name, progress: 0, state: invalid ? "error" : "uploading", error: invalid ?? undefined },
        ...current,
      ]);
      if (invalid) continue;
      uploadDocument(file, docType, (progress) => update(key, { progress }))
        .then(() => {
          update(key, { state: "done", progress: 1 });
          onUploaded();
        })
        .catch((err: unknown) =>
          update(key, { state: "error", error: err instanceof Error ? err.message : "Upload failed." }),
        );
    }
  };

  return (
    <section aria-label="Upload documents" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Upload PDFs</h2>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Type
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocType)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="policy">Policy / regulation</option>
            <option value="contract">Contract</option>
          </select>
        </label>
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Drop PDF files here or press Enter to browse"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          uploadFiles(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
        }`}
      >
        <FileUp aria-hidden className="mb-2 h-6 w-6 text-slate-400" />
        <p className="text-sm font-medium text-slate-700">
          Drag and drop PDFs, or <span className="text-indigo-600">browse</span>
        </p>
        <p className="mt-1 text-xs text-slate-500">PDF only, up to {MAX_UPLOAD_MB} MB each</p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => {
            if (e.target.files) uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <ul className="mt-3 space-y-2" aria-live="polite">
          {items.map((item) => (
            <li key={item.key} className="flex items-center gap-3 rounded-md bg-slate-50 px-3 py-2 text-sm">
              {item.state === "done" && <CheckCircle2 aria-hidden className="h-4 w-4 shrink-0 text-emerald-600" />}
              {item.state === "error" && <XCircle aria-hidden className="h-4 w-4 shrink-0 text-rose-600" />}
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-800">{item.name}</p>
                {item.state === "uploading" && (
                  <div
                    role="progressbar"
                    aria-label={`Uploading ${item.name}`}
                    aria-valuenow={Math.round(item.progress * 100)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200"
                  >
                    <div className="h-full bg-indigo-600 transition-all" style={{ width: `${item.progress * 100}%` }} />
                  </div>
                )}
                {item.state === "done" && <p className="text-xs text-slate-500">Uploaded, now processing…</p>}
                {item.state === "error" && <p className="text-xs text-rose-600">{item.error}</p>}
              </div>
              {item.state !== "uploading" && (
                <button
                  type="button"
                  aria-label={`Dismiss ${item.name}`}
                  onClick={() => setItems((current) => current.filter((i) => i.key !== item.key))}
                  className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
                >
                  <X aria-hidden className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
