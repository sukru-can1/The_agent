"use client";

import { useState } from "react";
import { Send, Check } from "lucide-react";
import { storeKnowledge } from "@/lib/api";

export default function CommentInput({ context }: { context?: string }) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "done">("idle");

  const handleSend = async () => {
    if (!value.trim()) return;
    setStatus("sending");
    const content = context ? `Re: ${context} — ${value}` : value;
    await storeKnowledge(content);
    setStatus("done");
    setValue("");
    setTimeout(() => setStatus("idle"), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        placeholder="Instruct the agent..."
        className="flex-1 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
        disabled={status === "sending"}
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || status === "sending"}
        className="p-1.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors disabled:opacity-30"
      >
        {status === "done" ? (
          <Check size={14} className="text-[var(--color-success)]" />
        ) : (
          <Send size={14} className="text-[var(--color-text-muted)]" />
        )}
      </button>
    </div>
  );
}
