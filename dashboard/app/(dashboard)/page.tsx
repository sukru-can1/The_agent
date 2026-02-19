"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Layers, Inbox, Zap, DollarSign, Send, Loader2, Power, Play, MessageSquare, ChevronDown, Paperclip, X, Image as ImageIcon, FileText } from "lucide-react";
import MetricTile from "@/components/cards/MetricTile";
import DecisionCard from "@/components/cards/DecisionCard";
import EditModal from "@/components/EditModal";
import EmptyState from "@/components/EmptyState";
import CategoryBadge from "@/components/ui/CategoryBadge";
import type { AgentStatus, Draft, AgentEvent, DlqEntry, AgentAction, Category } from "@/lib/types";
import { getCategory, extractDetail, timeAgo } from "@/lib/types";

function priorityLabel(p: number): "critical" | "high" | "medium" | "low" {
  if (p <= 1) return "critical";
  if (p <= 3) return "high";
  if (p <= 5) return "medium";
  return "low";
}

function classificationToPriority(c: string): "critical" | "high" | "medium" | "low" {
  if (c === "urgent") return "critical";
  if (c === "needs_response") return "high";
  if (c === "fyi") return "low";
  return "medium";
}

// Gemini cost rates (per 1M tokens, blended in/out)
function estimateCost(action: AgentAction): number {
  const model = action.model_used || "";
  let ratePerM = 0.5; // default flash
  if (model.includes("gemini-2.0-flash")) ratePerM = 0.5;
  else if (model.includes("gemini-2.5-flash")) ratePerM = 0.75;
  else if (model.includes("gemini-2.5-pro")) ratePerM = 11.25;
  else if (model.includes("gemini-3-pro")) ratePerM = 11.25;
  return ((action.input_tokens + action.output_tokens) * ratePerM) / 1_000_000;
}

interface Attachment {
  name: string;
  type: string;
  size: number;
  dataUrl: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  attachments?: Attachment[];
  timestamp?: string;
  loading?: boolean;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [sending, setSending] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load chat history on first open
  useEffect(() => {
    if (!open || historyLoaded) return;
    (async () => {
      try {
        const res = await fetch("/api/admin/chat-history?limit=10");
        if (!res.ok) return;
        const history = await res.json();
        const msgs: ChatMessage[] = [];
        for (const h of [...history].reverse()) {
          if (h.message_in) msgs.push({ role: "user", text: h.message_in, timestamp: h.timestamp });
          if (h.message_out) msgs.push({ role: "assistant", text: h.message_out, timestamp: h.timestamp });
        }
        setMessages(msgs);
      } catch {
        // API not available
      }
      setHistoryLoaded(true);
    })();
  }, [open, historyLoaded]);

  useEffect(() => {
    if (open) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  // Focus input on open
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  const readFileAsAttachment = (file: File): Promise<Attachment | null> => {
    return new Promise((resolve) => {
      if (file.size > 10 * 1024 * 1024) { resolve(null); return; }
      const reader = new FileReader();
      reader.onload = () => {
        resolve({ name: file.name, type: file.type, size: file.size, dataUrl: reader.result as string });
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  };

  const handleFiles = async (files: FileList | File[]) => {
    const newAttachments: Attachment[] = [];
    for (const file of Array.from(files)) {
      const att = await readFileAsAttachment(file);
      if (att) newAttachments.push(att);
    }
    if (newAttachments.length > 0) {
      setAttachments((prev) => [...prev, ...newAttachments].slice(0, 5));
    }
  };

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const item of Array.from(items)) {
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      await handleFiles(files);
    }
  };

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  const sendMessage = async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || sending) return;

    const currentAttachments = [...attachments];
    const displayText = text || `[${currentAttachments.map((a) => a.name).join(", ")}]`;
    setInput("");
    setAttachments([]);
    setMessages((prev) => [...prev, { role: "user", text: displayText, attachments: currentAttachments }]);
    setSending(true);
    setMessages((prev) => [...prev, { role: "assistant", text: "", loading: true }]);

    try {
      // Build message text with attachment info
      let fullText = text;
      if (currentAttachments.length > 0) {
        const attInfo = currentAttachments.map((a) => `[Attached: ${a.name} (${a.type}, ${formatFileSize(a.size)})]`).join("\n");
        fullText = fullText ? `${fullText}\n\n${attInfo}` : attInfo;
      }

      const injectRes = await fetch("/api/admin/inject-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "dashboard",
          event_type: "chat_message",
          text: fullText,
          attachments: currentAttachments.map((a) => ({ name: a.name, type: a.type, size: a.size, data: a.dataUrl })),
        }),
      });

      if (!injectRes.ok) {
        setMessages((prev) => prev.slice(0, -1).concat({ role: "assistant", text: "Failed to send message." }));
        setSending(false);
        return;
      }

      const { event_id } = await injectRes.json();

      let attempts = 0;
      const maxAttempts = 60;
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 2000));
        attempts++;
        try {
          const eventRes = await fetch(`/api/admin/events/${event_id}`);
          if (!eventRes.ok) continue;
          const eventData = await eventRes.json();
          if (eventData.status === "completed" || eventData.status === "failed") {
            const actionsRes = await fetch(`/api/admin/actions?event_id=${event_id}`);
            let responseText = eventData.status === "failed"
              ? `Error: ${eventData.error || "Processing failed"}`
              : "Done (no response text)";
            if (actionsRes.ok) {
              const actionsData = await actionsRes.json();
              if (actionsData.length > 0) {
                const details = actionsData[0].details;
                if (details) {
                  const parsed = typeof details === "string" ? JSON.parse(details) : details;
                  responseText = parsed.agent_response || parsed.result_summary || responseText;
                }
              }
            }
            setMessages((prev) => prev.slice(0, -1).concat({ role: "assistant", text: responseText }));
            break;
          }
        } catch { /* continue */ }
      }
      if (attempts >= maxAttempts) {
        setMessages((prev) => prev.slice(0, -1).concat({ role: "assistant", text: "Timed out waiting for response." }));
      }
    } catch {
      setMessages((prev) => prev.slice(0, -1).concat({ role: "assistant", text: "Network error." }));
    }
    setSending(false);
  };

  // Collapsed bar
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)] transition-colors w-full"
      >
        <MessageSquare size={14} className="text-[var(--color-accent)]" />
        <span className="text-xs text-[var(--color-text-muted)]">Chat with Agent</span>
        {sending && <Loader2 size={12} className="animate-spin text-[var(--color-accent)] ml-auto" />}
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      {/* Header — click to collapse */}
      <button
        onClick={() => setOpen(false)}
        className="w-full flex items-center gap-2 px-4 py-2.5 border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors"
      >
        <MessageSquare size={14} className="text-[var(--color-accent)]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] flex-1 text-left">
          Chat with Agent
        </span>
        <ChevronDown size={14} className="text-[var(--color-text-dim)]" />
      </button>

      {/* Messages */}
      <div className="h-64 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <p className="text-xs text-[var(--color-text-dim)] text-center py-8">
            Send a message to instruct the agent
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] px-3 py-2 rounded-lg text-xs whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-[var(--color-accent)]/20 text-[var(--color-text)]"
                  : "bg-[var(--color-surface-hover)] text-[var(--color-text)]"
              }`}
            >
              {msg.loading ? (
                <span className="flex items-center gap-2 text-[var(--color-text-muted)]">
                  <Loader2 size={12} className="animate-spin" />
                  Thinking...
                </span>
              ) : (
                <>
                  {msg.text}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="mt-1.5 space-y-1">
                      {msg.attachments.map((att, j) => (
                        <div key={j} className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
                          {att.type.startsWith("image/") ? <ImageIcon size={10} /> : <FileText size={10} />}
                          {att.name} ({formatFileSize(att.size)})
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Attachment preview strip */}
      {attachments.length > 0 && (
        <div className="px-3 py-2 border-t border-[var(--color-border)] flex flex-wrap gap-2">
          {attachments.map((att, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--color-surface-hover)] text-[10px] text-[var(--color-text-muted)]"
            >
              {att.type.startsWith("image/") ? <ImageIcon size={10} /> : <FileText size={10} />}
              <span className="max-w-[120px] truncate">{att.name}</span>
              <button onClick={() => removeAttachment(i)} className="hover:text-[var(--color-text)] transition-colors">
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-[var(--color-border)] px-3 py-2 flex items-center gap-2">
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          multiple
          accept="image/*,.pdf,.csv,.xlsx,.xls,.doc,.docx,.txt,.json"
          onChange={(e) => { if (e.target.files) handleFiles(e.target.files); e.target.value = ""; }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={sending}
          className="p-1.5 rounded-md text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] disabled:opacity-40 transition-colors"
          title="Attach file"
        >
          <Paperclip size={14} />
        </button>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
          onPaste={handlePaste}
          placeholder="Type an instruction or paste an image..."
          disabled={sending}
          className="flex-1 bg-transparent text-xs text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] outline-none"
        />
        <button
          onClick={sendMessage}
          disabled={sending || (!input.trim() && attachments.length === 0)}
          className="p-1.5 rounded-md bg-[var(--color-accent)]/20 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/30 disabled:opacity-40 transition-colors"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}

export default function CommandCenter() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [dlq, setDlq] = useState<DlqEntry[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [editingDraft, setEditingDraft] = useState<Draft | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [statusRes, draftsRes, eventsRes, dlqRes, actionsRes] = await Promise.all([
        fetch("/api/admin/status"),
        fetch("/api/admin/drafts?status=pending"),
        fetch("/api/admin/events?status=pending&limit=20"),
        fetch("/api/admin/dlq"),
        fetch("/api/admin/actions?limit=15"),
      ]);

      if (statusRes.ok) {
        setStatus(await statusRes.json());
        setDrafts(await draftsRes.json());
        setEvents(await eventsRes.json());
        setDlq(await dlqRes.json());
        setActions(await actionsRes.json());
      }
    } catch {
      // API not available
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // Estimate today's cost from actions (Gemini rates)
  const todayCost = actions.reduce((sum, a) => sum + estimateCost(a), 0);

  const isPaused = status?.is_paused ?? false;

  const togglePause = async () => {
    const endpoint = isPaused ? "/api/admin/queue/resume" : "/api/admin/queue/pause";
    await fetch(endpoint, { method: "POST" });
    fetchAll();
  };

  return (
    <div className="space-y-5">
      {/* Agent status bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${isPaused ? "bg-red-500" : "bg-emerald-500 animate-pulse"}`} />
          <span className="text-sm font-medium">
            {isPaused ? "Agent paused" : "Agent running"}
          </span>
          {isPaused && (
            <span className="text-xs text-[var(--color-text-muted)]">
              Events are queued but not processed
            </span>
          )}
        </div>
        <button
          onClick={togglePause}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-all btn-press ${
            isPaused
              ? "bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/30"
              : "bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/30"
          }`}
        >
          {isPaused ? <Play size={14} /> : <Power size={14} />}
          {isPaused ? "Resume Agent" : "Pause Agent"}
        </button>
      </div>

      {/* Metric tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricTile
          icon={Layers}
          label="Queue"
          value={status?.queue_depth ?? 0}
          color="bg-indigo-500/10 text-indigo-400"
        />
        <MetricTile
          icon={Inbox}
          label="Drafts"
          value={status?.pending_drafts ?? 0}
          color="bg-amber-500/10 text-amber-400"
        />
        <MetricTile
          icon={Zap}
          label="Today"
          value={actions.length}
          color="bg-emerald-500/10 text-emerald-400"
        />
        <MetricTile
          icon={DollarSign}
          label="Cost"
          value={`$${todayCost.toFixed(2)}`}
          color="bg-purple-500/10 text-purple-400"
        />
      </div>

      {/* Chat widget */}
      <ChatWidget />

      {/* Main grid: Decisions (2/3) + Feed (1/3) */}
      <div className="grid lg:grid-cols-3 gap-5">
        {/* Decisions column */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Decisions ({drafts.length + events.filter((e) => e.priority <= 3).length + dlq.length})
          </h2>

          {/* Drafts */}
          {drafts.map((d) => (
            <DecisionCard
              key={`draft-${d.id}`}
              variant="draft"
              category={getCategory("gmail", "email_draft")}
              title={d.subject || "No subject"}
              subtitle={`From: ${d.from_address}`}
              body={d.draft_body}
              priority={classificationToPriority(d.classification)}
              timestamp={d.created_at}
              source="gmail"
              actions={[
                {
                  label: "Approve",
                  variant: "primary",
                  onClick: async () => {
                    await fetch(`/api/admin/drafts/${d.id}/approve`, { method: "POST" });
                    setDrafts((prev) => prev.filter((x) => x.id !== d.id));
                  },
                },
                {
                  label: "Edit",
                  variant: "secondary",
                  onClick: async () => setEditingDraft(d),
                },
                {
                  label: "Skip",
                  variant: "danger",
                  onClick: async () => {
                    await fetch(`/api/admin/drafts/${d.id}/reject`, { method: "POST" });
                    setDrafts((prev) => prev.filter((x) => x.id !== d.id));
                  },
                },
              ]}
            />
          ))}

          {/* Alert events (priority <= 3) */}
          {events
            .filter((e) => e.priority <= 3)
            .map((e) => (
              <DecisionCard
                key={`alert-${e.id}`}
                variant="alert"
                category={getCategory(e.source, e.event_type)}
                title={e.event_type.replace(/_/g, " ")}
                subtitle={`Source: ${e.source}`}
                body={
                  e.error
                    ? `Priority ${e.priority} event. Error: ${e.error}`
                    : `Priority ${e.priority} event from ${e.source}`
                }
                priority={priorityLabel(e.priority)}
                timestamp={e.created_at}
                source={e.source}
                payload={e.payload}
                actions={[
                  {
                    label: "Dismiss",
                    variant: "secondary",
                    onClick: async () => {
                      setEvents((prev) => prev.filter((x) => x.id !== e.id));
                    },
                  },
                ]}
              />
            ))}

          {/* DLQ entries */}
          {dlq.map((d) => {
            const lastError =
              d.error_history.length > 0
                ? d.error_history[d.error_history.length - 1].error
                : "Unknown error";
            return (
              <DecisionCard
                key={`dlq-${d.id}`}
                variant="dlq"
                category={getCategory(d.source, d.event_type)}
                title={`Failed: ${d.event_type.replace(/_/g, " ")}`}
                subtitle={`${d.retry_count} retries exhausted`}
                body={`Source: ${d.source}\nLast error: ${lastError}\nRetried ${d.retry_count} times.`}
                priority="high"
                timestamp={d.created_at}
                source={d.source}
                actions={[
                  {
                    label: "Retry",
                    variant: "primary",
                    onClick: async () => {
                      await fetch(`/api/admin/dlq/${d.id}/retry`, { method: "POST" });
                      setDlq((prev) => prev.filter((x) => x.id !== d.id));
                    },
                  },
                  {
                    label: "Resolve",
                    variant: "secondary",
                    onClick: async () => {
                      await fetch(`/api/admin/dlq/${d.id}/resolve`, { method: "POST" });
                      setDlq((prev) => prev.filter((x) => x.id !== d.id));
                    },
                  },
                ]}
              />
            );
          })}

          {drafts.length === 0 &&
            events.filter((e) => e.priority <= 3).length === 0 &&
            dlq.length === 0 && <EmptyState />}
        </div>

        {/* Activity feed column */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Recent Activity
          </h2>
          <div className="space-y-1">
            {actions.slice(0, 20).map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-2 px-3 py-2 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-border-hover)] transition-colors"
              >
                <CategoryBadge category={getCategory(a.system, a.action_type)} />
                <span className="flex-1 text-xs truncate">
                  {a.action_type.replace(/_/g, " ")}
                </span>
                <span className="text-[10px] text-[var(--color-text-dim)] font-mono shrink-0">
                  {timeAgo(a.timestamp)}
                </span>
              </div>
            ))}
            {actions.length === 0 && (
              <p className="text-xs text-[var(--color-text-dim)] px-3 py-4 text-center">
                No recent activity
              </p>
            )}
          </div>

          {/* Info events */}
          {events
            .filter((e) => e.priority > 3)
            .slice(0, 5)
            .map((e) => (
              <div
                key={e.id}
                className="flex items-center gap-2 px-3 py-2 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)]"
              >
                <CategoryBadge category={getCategory(e.source, e.event_type)} />
                <span className="flex-1 text-xs truncate">
                  {e.event_type.replace(/_/g, " ")}
                </span>
                <span className="text-[10px] text-[var(--color-text-dim)] font-mono shrink-0">
                  {timeAgo(e.created_at)}
                </span>
              </div>
            ))}
        </div>
      </div>

      {/* Edit Modal */}
      {editingDraft && (
        <EditModal
          title={editingDraft.subject}
          subtitle={`To: ${editingDraft.from_address}`}
          originalBody={editingDraft.draft_body}
          onClose={() => setEditingDraft(null)}
          onSave={async (edited) => {
            await fetch(`/api/admin/drafts/${editingDraft.id}/approve`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ edited_body: edited }),
            });
            setDrafts((prev) => prev.filter((x) => x.id !== editingDraft.id));
            setEditingDraft(null);
          }}
        />
      )}
    </div>
  );
}
