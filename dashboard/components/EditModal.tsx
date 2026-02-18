"use client";

import { useState } from "react";
import { X } from "lucide-react";

interface Props {
  title: string;
  subtitle?: string;
  originalBody: string;
  onSave: (editedBody: string) => Promise<void>;
  onClose: () => void;
}

export default function EditModal({
  title,
  subtitle,
  originalBody,
  onSave,
  onClose,
}: Props) {
  const [body, setBody] = useState(originalBody);
  const [saving, setSaving] = useState(false);

  const changed = body !== originalBody;
  const charDiff = body.length - originalBody.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl bg-[var(--color-surface)] rounded-3xl border border-[var(--color-border)] shadow-2xl card-enter overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-5 pb-3 flex items-start justify-between">
          <div>
            <h2 className="font-bold text-lg">Edit Draft</h2>
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
              {title}
            </p>
            {subtitle && (
              <p className="text-xs text-[var(--color-text-dim)]">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Editor */}
        <div className="px-6 pb-4">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={12}
            className="w-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-2xl p-4 text-sm font-mono leading-relaxed resize-none focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            autoFocus
          />
          {changed && (
            <p className="text-xs text-[var(--color-text-dim)] mt-1">
              {charDiff > 0 ? `+${charDiff}` : charDiff} characters
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 pb-5 flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] transition-all btn-press"
          >
            Cancel
          </button>
          <button
            disabled={!changed || saving}
            onClick={async () => {
              setSaving(true);
              await onSave(body);
              setSaving(false);
            }}
            className="px-6 py-2 rounded-xl text-sm font-medium bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white shadow-lg shadow-indigo-500/10 transition-all btn-press disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Saving...
              </span>
            ) : (
              "Save & Approve"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
