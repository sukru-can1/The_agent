"use client";

import { Activity, AlertTriangle, Inbox, Layers, Zap } from "lucide-react";
import type { AgentStatus } from "@/lib/types";

function Stat({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-3">
      <div className={`p-2 rounded-xl ${color}`}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium">
          {label}
        </p>
        <p className="text-xl font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}

export default function StatusBar({
  status,
  connected,
}: {
  status: AgentStatus | null;
  connected: boolean;
}) {
  return (
    <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-xl">
      <div className="max-w-4xl mx-auto flex items-center justify-between px-4">
        {/* Logo / Name */}
        <div className="flex items-center gap-3 py-4">
          <div className="relative">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-indigo-500/20">
              A
            </div>
            <div
              className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[var(--color-surface)] ${
                connected
                  ? "bg-[var(--color-success)]"
                  : "bg-[var(--color-danger)]"
              }`}
            />
          </div>
          <div>
            <h1 className="font-bold text-base leading-tight">The Agent1</h1>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              {connected ? "Online" : "Connecting..."}
            </p>
          </div>
        </div>

        {/* Stats */}
        {status && (
          <div className="flex items-center divide-x divide-[var(--color-border)]">
            <Stat
              icon={Layers}
              label="Queue"
              value={status.queue_depth}
              color="bg-indigo-500/10 text-indigo-400"
            />
            <Stat
              icon={Inbox}
              label="Drafts"
              value={status.pending_drafts}
              color="bg-amber-500/10 text-amber-400"
            />
            <Stat
              icon={AlertTriangle}
              label="DLQ"
              value={status.dlq_count}
              color={
                status.dlq_count > 0
                  ? "bg-red-500/10 text-red-400"
                  : "bg-emerald-500/10 text-emerald-400"
              }
            />
          </div>
        )}
      </div>
    </header>
  );
}
