"use client";

import { useCallback, useEffect, useState } from "react";
import {
  X,
  Send,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Pencil,
  Clock,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { fetchDraft, reviseDraft, approveAndSendDraft } from "@/lib/api";
import { timeAgo } from "@/lib/types";

interface Revision {
  instruction: string;
  model_used?: string;
  input_tokens?: number;
  output_tokens?: number;
  timestamp?: string;
}

interface DraftFull {
  id: number;
  gmail_message_id: string;
  gmail_thread_id: string;
  from_address: string;
  to_address: string;
  subject: string;
  original_body: string | null;
  draft_body: string;
  edited_body: string | null;
  status: string;
  classification: string;
  context_used: {
    context_notes?: string;
    revisions?: Revision[];
  } | null;
  created_at: string;
  approved_at: string | null;
  sent_at: string | null;
}

interface Props {
  draftId: number;
  onClose: () => void;
  onSent: () => void;
}

export default function DraftRefineModal({ draftId, onClose, onSent }: Props) {
  const [draft, setDraft] = useState<DraftFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Revision
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);

  // Manual edit
  const [editMode, setEditMode] = useState(false);
  const [manualBody, setManualBody] = useState("");

  // Send
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [sendError, setSendError] = useState("");

  // Original email collapse
  const [showOriginal, setShowOriginal] = useState(false);

  const loadDraft = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchDraft(draftId);
      setDraft(data);
      setManualBody(data.edited_body || data.draft_body);
    } catch {
      setError("Failed to load draft details");
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    loadDraft();
  }, [loadDraft]);

  const currentBody = draft
    ? editMode
      ? manualBody
      : draft.edited_body || draft.draft_body
    : "";

  const revisions = draft?.context_used?.revisions || [];

  const handleRevise = async () => {
    if (!instruction.trim() || !draft) return;
    setRevising(true);
    setSendError("");
    try {
      const result = await reviseDraft(draft.id, instruction.trim());
      // Refresh draft to get updated body and revision history
      const updated = await fetchDraft(draft.id);
      setDraft(updated);
      setManualBody(updated.edited_body || updated.draft_body);
      setInstruction("");
      setEditMode(false);
    } catch {
      setSendError("Revision failed — try again");
    } finally {
      setRevising(false);
    }
  };

  const handleSend = async () => {
    if (!draft) return;
    setSending(true);
    setSendError("");
    try {
      const finalBody = editMode ? manualBody : undefined;
      await approveAndSendDraft(draft.id, finalBody);
      setSent(true);
      setTimeout(() => {
        onSent();
        onClose();
      }, 1500);
    } catch (e) {
      setSendError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  };

  // Keyboard shortcut: Ctrl+Enter to send
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !sending && !sent && draft) {
        handleSend();
      }
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[90vh] bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] shadow-2xl card-enter flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-5 pb-3 flex items-start justify-between shrink-0 border-b border-[var(--color-border)]">
          <div className="min-w-0">
            <h2 className="font-bold text-lg truncate">
              {draft ? `Re: ${draft.subject || "(no subject)"}` : "Loading..."}
            </h2>
            {draft && (
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                To: {draft.from_address}
                <span className="ml-3 text-[var(--color-text-dim)]">
                  {draft.classification} &middot; {timeAgo(draft.created_at)}
                </span>
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-[var(--color-surface-hover)] transition-colors shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 size={24} className="animate-spin text-[var(--color-accent)]" />
            </div>
          ) : error ? (
            <div className="text-center py-10 text-red-400 text-sm">{error}</div>
          ) : draft ? (
            <>
              {/* Original email (collapsible) */}
              {draft.original_body && (
                <div className="rounded-lg border border-[var(--color-border)] overflow-hidden">
                  <button
                    onClick={() => setShowOriginal(!showOriginal)}
                    className="w-full px-4 py-2.5 flex items-center gap-2 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] transition-colors"
                  >
                    {showOriginal ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Original Email
                  </button>
                  {showOriginal && (
                    <div className="px-4 pb-3 text-xs text-[var(--color-text-dim)] font-mono leading-relaxed whitespace-pre-wrap border-t border-[var(--color-border)] bg-[var(--color-bg)] max-h-48 overflow-y-auto">
                      {draft.original_body}
                    </div>
                  )}
                </div>
              )}

              {/* Current draft */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-[var(--color-text-muted)]">
                    Current Draft
                  </span>
                  {draft.edited_body ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400">
                      Revised
                    </span>
                  ) : (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-text-dim)]">
                      Original
                    </span>
                  )}
                  {!editMode && (
                    <button
                      onClick={() => setEditMode(true)}
                      className="ml-auto text-[10px] flex items-center gap-1 text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
                    >
                      <Pencil size={10} />
                      Edit manually
                    </button>
                  )}
                  {editMode && (
                    <button
                      onClick={() => {
                        setEditMode(false);
                        setManualBody(draft.edited_body || draft.draft_body);
                      }}
                      className="ml-auto text-[10px] text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
                    >
                      Cancel editing
                    </button>
                  )}
                </div>

                {editMode ? (
                  <textarea
                    value={manualBody}
                    onChange={(e) => setManualBody(e.target.value)}
                    rows={10}
                    className="w-full bg-[var(--color-bg)] border border-[var(--color-accent)]/40 rounded-lg p-4 text-sm font-mono leading-relaxed resize-none focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                    autoFocus
                  />
                ) : (
                  <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg p-4 text-sm font-mono leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {currentBody}
                  </div>
                )}
              </div>

              {/* AI Refinement */}
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Sparkles
                    size={14}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)]"
                  />
                  <input
                    type="text"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey && instruction.trim()) {
                        e.preventDefault();
                        handleRevise();
                      }
                    }}
                    placeholder="make it more formal, add tracking number, shorter..."
                    disabled={revising}
                    className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-sm placeholder:text-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-accent)] transition-colors disabled:opacity-50"
                  />
                </div>
                <button
                  onClick={handleRevise}
                  disabled={!instruction.trim() || revising}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium bg-indigo-500/15 text-indigo-400 hover:bg-indigo-500/25 transition-all btn-press disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
                >
                  {revising ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      Revising...
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} />
                      Revise
                    </>
                  )}
                </button>
              </div>

              {/* Revision history */}
              {revisions.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[10px] font-medium text-[var(--color-text-dim)] uppercase tracking-wider">
                    Revision History
                  </span>
                  {revisions.map((rev, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]"
                    >
                      <span className="text-[var(--color-text-dim)] font-mono w-4 text-right shrink-0">
                        {i + 1}.
                      </span>
                      <span className="truncate">&ldquo;{rev.instruction}&rdquo;</span>
                      {rev.model_used && (
                        <span className="text-[10px] text-[var(--color-text-dim)] shrink-0">
                          {rev.model_used.split("-").slice(0, 2).join("-")}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 flex items-center justify-between border-t border-[var(--color-border)] shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm font-medium bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] transition-all btn-press"
          >
            Cancel
          </button>

          <div className="flex items-center gap-3">
            {sendError && (
              <span className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle size={12} />
                {sendError}
              </span>
            )}

            {sent ? (
              <span className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
                <CheckCircle2 size={16} />
                Sent!
              </span>
            ) : (
              <button
                onClick={handleSend}
                disabled={sending || !draft}
                className="px-6 py-2.5 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/15 transition-all btn-press disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {sending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send size={14} />
                    Approve & Send
                    <span className="text-[10px] opacity-60 ml-1">Ctrl+Enter</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
