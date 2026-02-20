"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Send,
  Loader2,
  MessageSquare,
  ChevronUp,
  Paperclip,
  X,
  Image as ImageIcon,
  FileText,
  Minus,
  Sparkles,
} from "lucide-react";

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

/* ------------------------------------------------------------------ */
/*  Floating pill button — mouse-reactive, hugs bottom of viewport    */
/* ------------------------------------------------------------------ */
function FloatingPill({
  onClick,
  sending,
}: {
  onClick: () => void;
  sending: boolean;
}) {
  const pillRef = useRef<HTMLButtonElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0, gx: 50, gy: 50 });
  const raf = useRef(0);

  useEffect(() => {
    const el = pillRef.current;
    if (!el) return;

    const onMove = (e: MouseEvent) => {
      cancelAnimationFrame(raf.current);
      raf.current = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = (e.clientX - cx) / rect.width;
        const dy = (e.clientY - cy) / rect.height;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const influence = Math.max(0, 1 - dist / 4);
        setTilt({
          x: dx * 12 * influence,
          y: dy * -8 * influence,
          gx: 50 + dx * 30,
          gy: 50 + dy * 30,
        });
      });
    };

    const onLeave = () => {
      setTilt({ x: 0, y: 0, gx: 50, gy: 50 });
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseleave", onLeave);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseleave", onLeave);
      cancelAnimationFrame(raf.current);
    };
  }, []);

  return (
    <button
      ref={pillRef}
      onClick={onClick}
      className="chat-pill group fixed z-40 bottom-3 left-20 flex items-center gap-2.5 px-5 py-2.5 text-xs font-medium transition-all duration-300 ease-out"
      style={{
        transform: `perspective(600px) rotateY(${tilt.x}deg) rotateX(${tilt.y}deg)`,
        borderRadius: "12px",
        background: `radial-gradient(ellipse at ${tilt.gx}% ${tilt.gy}%, rgba(129,140,248,0.45), rgba(99,102,241,0.2) 70%)`,
        border: "1px solid rgba(129,140,248,0.35)",
        backdropFilter: "blur(16px)",
        boxShadow: `0 4px 24px rgba(129,140,248,${0.15 + Math.abs(tilt.x) * 0.01}), 0 0 0 1px rgba(129,140,248,0.1), inset 0 1px 0 rgba(255,255,255,0.08)`,
      }}
    >
      {/* Animated orb */}
      <span className="chat-orb relative flex items-center justify-center w-6 h-6">
        <span
          className="absolute inset-0 rounded-full opacity-60"
          style={{
            background:
              "conic-gradient(from 0deg, #818cf8, #6366f1, #a78bfa, #818cf8)",
            animation: "orb-spin 3s linear infinite",
          }}
        />
        <span className="absolute inset-[2px] rounded-full bg-[#12121a]" />
        <Sparkles
          size={12}
          className="relative z-10 text-[var(--color-accent)]"
          style={{ animation: "orb-breathe 2s ease-in-out infinite" }}
        />
      </span>

      <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors">
        Ask Agent
      </span>

      <ChevronUp
        size={14}
        className="text-[var(--color-text-dim)] group-hover:text-[var(--color-accent)] transition-all duration-300 group-hover:-translate-y-0.5"
      />

      {sending && (
        <span className="flex items-center gap-1 text-amber-400 text-[10px]">
          <Loader2 size={10} className="animate-spin" />
        </span>
      )}

      {/* Edge glow lines */}
      <span
        className="absolute -top-px left-4 right-4 h-px"
        style={{
          background: `linear-gradient(90deg, transparent, rgba(129,140,248,${0.3 + Math.abs(tilt.x) * 0.03}) 50%, transparent)`,
        }}
      />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ChatPanel                                                     */
/* ------------------------------------------------------------------ */
export default function ChatPanel() {
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
          if (h.message_in)
            msgs.push({
              role: "user",
              text: h.message_in,
              timestamp: h.timestamp,
            });
          if (h.message_out)
            msgs.push({
              role: "assistant",
              text: h.message_out,
              timestamp: h.timestamp,
            });
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

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 200);
  }, [open]);

  const readFileAsAttachment = (file: File): Promise<Attachment | null> => {
    return new Promise((resolve) => {
      if (file.size > 10 * 1024 * 1024) {
        resolve(null);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        resolve({
          name: file.name,
          type: file.type,
          size: file.size,
          dataUrl: reader.result as string,
        });
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
    const displayText =
      text || `[${currentAttachments.map((a) => a.name).join(", ")}]`;
    setInput("");
    setAttachments([]);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: displayText, attachments: currentAttachments },
    ]);
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", text: "", loading: true },
    ]);

    try {
      let fullText = text;
      if (currentAttachments.length > 0) {
        const attInfo = currentAttachments
          .map(
            (a) =>
              `[Attached: ${a.name} (${a.type}, ${formatFileSize(a.size)})]`,
          )
          .join("\n");
        fullText = fullText ? `${fullText}\n\n${attInfo}` : attInfo;
      }

      const injectRes = await fetch("/api/admin/inject-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "dashboard",
          event_type: "chat_message",
          text: fullText,
          attachments: currentAttachments.map((a) => ({
            name: a.name,
            type: a.type,
            size: a.size,
            data: a.dataUrl,
          })),
        }),
      });

      if (!injectRes.ok) {
        setMessages((prev) =>
          prev
            .slice(0, -1)
            .concat({ role: "assistant", text: "Failed to send message." }),
        );
        setSending(false);
        return;
      }

      const { event_id } = await injectRes.json();

      let attempts = 0;
      const maxAttempts = 90;
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 2000));
        attempts++;
        try {
          const eventRes = await fetch(`/api/admin/events/${event_id}`);
          if (!eventRes.ok) continue;
          const eventData = await eventRes.json();
          if (
            eventData.status === "completed" ||
            eventData.status === "failed"
          ) {
            const actionsRes = await fetch(
              `/api/admin/actions?event_id=${event_id}`,
            );
            let responseText =
              eventData.status === "failed"
                ? `Error: ${eventData.error || "Processing failed"}`
                : "Done (no response text)";
            if (actionsRes.ok) {
              const actionsData = await actionsRes.json();
              if (actionsData.length > 0) {
                const details = actionsData[0].details;
                if (details) {
                  const parsed =
                    typeof details === "string"
                      ? JSON.parse(details)
                      : details;
                  responseText =
                    parsed.agent_response ||
                    parsed.result_summary ||
                    responseText;
                }
              }
            }
            setMessages((prev) =>
              prev
                .slice(0, -1)
                .concat({ role: "assistant", text: responseText }),
            );
            break;
          }
        } catch {
          /* continue */
        }
      }
      if (attempts >= maxAttempts) {
        setMessages((prev) =>
          prev.slice(0, -1).concat({
            role: "assistant",
            text: "Timed out waiting for response. Check activity feed.",
          }),
        );
      }
    } catch {
      setMessages((prev) =>
        prev
          .slice(0, -1)
          .concat({ role: "assistant", text: "Network error." }),
      );
    }
    setSending(false);
  };

  /* Closed — floating pill at bottom center */
  if (!open) {
    return <FloatingPill onClick={() => setOpen(true)} sending={sending} />;
  }

  /* Open — panel slides up from bottom */
  return (
    <div
      className="fixed bottom-0 left-16 right-0 z-40 flex flex-col border-t border-[var(--color-border)]"
      style={{
        height: "360px",
        background:
          "linear-gradient(180deg, rgba(18,18,26,0.97) 0%, rgba(10,10,15,0.99) 100%)",
        backdropFilter: "blur(20px)",
        boxShadow:
          "0 -8px 40px rgba(0,0,0,0.4), 0 -1px 0 rgba(129,140,248,0.1)",
        animation: "panel-up 0.25s ease-out",
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-[var(--color-border)] shrink-0">
        <span className="chat-orb relative flex items-center justify-center w-5 h-5">
          <span
            className="absolute inset-0 rounded-full opacity-50"
            style={{
              background:
                "conic-gradient(from 0deg, #818cf8, #6366f1, #a78bfa, #818cf8)",
              animation: "orb-spin 3s linear infinite",
            }}
          />
          <span className="absolute inset-[1.5px] rounded-full bg-[#12121a]" />
          <Sparkles
            size={10}
            className="relative z-10 text-[var(--color-accent)]"
          />
        </span>
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] flex-1">
          Agent Console
        </span>
        {sending && (
          <span className="flex items-center gap-1.5 text-[10px] text-amber-400">
            <Loader2 size={10} className="animate-spin" />
            Processing...
          </span>
        )}
        <button
          onClick={() => setOpen(false)}
          className="p-1 rounded hover:bg-[var(--color-surface-hover)] transition-colors text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]"
          title="Minimize"
        >
          <Minus size={14} />
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5">
        {messages.length === 0 && (
          <p className="text-xs text-[var(--color-text-dim)] text-center py-6">
            Send instructions to the agent &mdash; responses appear here
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] px-3 py-2 rounded-lg text-xs leading-relaxed whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-[var(--color-accent)]/15 text-[var(--color-text)] border border-[var(--color-accent)]/20"
                  : "bg-[var(--color-bg)] text-[var(--color-text)] border border-[var(--color-border)]"
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
                        <div
                          key={j}
                          className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]"
                        >
                          {att.type.startsWith("image/") ? (
                            <ImageIcon size={10} />
                          ) : (
                            <FileText size={10} />
                          )}
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
        <div className="px-4 py-1.5 border-t border-[var(--color-border)] flex flex-wrap gap-2 shrink-0">
          {attachments.map((att, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--color-surface-hover)] text-[10px] text-[var(--color-text-muted)]"
            >
              {att.type.startsWith("image/") ? (
                <ImageIcon size={10} />
              ) : (
                <FileText size={10} />
              )}
              <span className="max-w-[120px] truncate">{att.name}</span>
              <button
                onClick={() => removeAttachment(i)}
                className="hover:text-[var(--color-text)] transition-colors"
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-[var(--color-border)] px-4 py-2.5 flex items-center gap-2 shrink-0 bg-[var(--color-bg)]/50">
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          multiple
          accept="image/*,.pdf,.csv,.xlsx,.xls,.doc,.docx,.txt,.json"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            e.target.value = "";
          }}
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
          placeholder="Instruct the agent... (Enter to send)"
          disabled={sending}
          className="flex-1 bg-transparent text-xs text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] outline-none"
        />
        <button
          onClick={sendMessage}
          disabled={sending || (!input.trim() && attachments.length === 0)}
          className="px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--color-accent)]/15 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/25 disabled:opacity-40 transition-colors flex items-center gap-1.5"
        >
          <Send size={12} />
          Send
        </button>
      </div>
    </div>
  );
}
