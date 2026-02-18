"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ScrollText, Clock, Cpu, Zap } from "lucide-react";
import Link from "next/link";

interface Action {
  id: number;
  timestamp: string;
  system: string;
  action_type: string;
  outcome: string;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

const outcomeColors: Record<string, string> = {
  success: "text-emerald-400",
  blocked: "text-amber-400",
  failed: "text-red-400",
};

const systemColors: Record<string, string> = {
  gmail: "bg-blue-500/10 text-blue-400",
  freshdesk: "bg-amber-500/10 text-amber-400",
  gchat: "bg-emerald-500/10 text-emerald-400",
  feedbacks: "bg-purple-500/10 text-purple-400",
  starinfinity: "bg-pink-500/10 text-pink-400",
  scheduler: "bg-indigo-500/10 text-indigo-400",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function ActionsPage() {
  const [actions, setActions] = useState<Action[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/actions?limit=100");
      if (res.ok) {
        setActions(await res.json());
      }
    } catch {
      // API not available
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto flex items-center gap-4 px-4 py-4">
          <Link
            href="/"
            className="p-2 rounded-xl hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            <ArrowLeft size={18} className="text-[var(--color-text-muted)]" />
          </Link>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
              <ScrollText size={20} />
            </div>
            <div>
              <h1 className="font-bold text-base">Action Log</h1>
              <p className="text-[11px] text-[var(--color-text-muted)]">
                Audit trail of all agent actions
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : actions.length === 0 ? (
          <div className="text-center py-20 text-[var(--color-text-muted)]">
            <ScrollText size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">No actions recorded yet</p>
            <p className="text-sm mt-1">Actions will appear as the agent processes events.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {actions.map((a) => (
              <div
                key={a.id}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 flex items-center gap-4"
              >
                {/* System badge */}
                <span
                  className={`px-2 py-0.5 rounded-lg text-[10px] font-medium shrink-0 ${
                    systemColors[a.system] || "bg-gray-500/10 text-gray-400"
                  }`}
                >
                  {a.system}
                </span>

                {/* Action type */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {a.action_type.replace(/_/g, " ")}
                  </p>
                </div>

                {/* Model */}
                {a.model_used && (
                  <div className="hidden sm:flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
                    <Cpu size={10} />
                    {a.model_used.split("-").slice(0, 2).join("-")}
                  </div>
                )}

                {/* Tokens */}
                {(a.input_tokens > 0 || a.output_tokens > 0) && (
                  <div className="hidden sm:flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
                    <Zap size={10} />
                    {((a.input_tokens + a.output_tokens) / 1000).toFixed(1)}K
                  </div>
                )}

                {/* Latency */}
                {a.latency_ms > 0 && (
                  <div className="flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
                    <Clock size={10} />
                    {a.latency_ms > 1000
                      ? `${(a.latency_ms / 1000).toFixed(1)}s`
                      : `${a.latency_ms}ms`}
                  </div>
                )}

                {/* Outcome */}
                <span
                  className={`text-[10px] font-medium ${
                    outcomeColors[a.outcome] || "text-[var(--color-text-dim)]"
                  }`}
                >
                  {a.outcome}
                </span>

                {/* Time */}
                <span className="text-[10px] text-[var(--color-text-dim)] w-14 text-right shrink-0">
                  {timeAgo(a.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
