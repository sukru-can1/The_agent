"use client";

import { RefreshCw, Layers, Inbox, AlertTriangle } from "lucide-react";
import type { AgentStatus, Category } from "@/lib/types";
import { CATEGORY_CONFIG } from "@/lib/types";

interface Props {
  title: string;
  status: AgentStatus | null;
  connected: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  activeCategory: Category | null;
  onCategoryChange: (cat: Category | null) => void;
}

const categories: Category[] = ["cs", "finance", "operations", "website", "marketing", "system"];

export default function Topbar({
  title,
  status,
  connected,
  onRefresh,
  refreshing,
  activeCategory,
  onCategoryChange,
}: Props) {
  return (
    <header className="h-[var(--topbar-height)] border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-xl flex items-center px-5 gap-4">
      {/* Title */}
      <h1 className="font-semibold text-sm whitespace-nowrap">{title}</h1>

      {/* Connection dot */}
      <span
        className={`w-2 h-2 rounded-full ${
          connected ? "bg-[var(--color-success)]" : "bg-[var(--color-danger)]"
        }`}
        title={connected ? "Connected" : "Disconnected"}
      />

      {/* Status pills */}
      {status && (
        <div className="flex items-center gap-2">
          <StatusPill icon={Layers} value={status.queue_depth} label="Q" />
          <StatusPill icon={Inbox} value={status.pending_drafts} label="D" />
          <StatusPill
            icon={AlertTriangle}
            value={status.dlq_count}
            label="E"
            warn={status.dlq_count > 0}
          />
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Category filters */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => onCategoryChange(null)}
          className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
            activeCategory === null
              ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
              : "text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]"
          }`}
        >
          All
        </button>
        {categories.map((cat) => {
          const cfg = CATEGORY_CONFIG[cat];
          return (
            <button
              key={cat}
              onClick={() => onCategoryChange(activeCategory === cat ? null : cat)}
              className="px-2 py-1 rounded text-[10px] font-medium transition-colors"
              style={{
                color: activeCategory === cat ? cfg.color : undefined,
                backgroundColor: activeCategory === cat ? `${cfg.color}20` : undefined,
              }}
            >
              {cfg.label}
            </button>
          );
        })}
      </div>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        className="p-2 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
        title="Refresh"
      >
        <RefreshCw
          size={14}
          className={`text-[var(--color-text-muted)] ${refreshing ? "animate-spin" : ""}`}
        />
      </button>
    </header>
  );
}

function StatusPill({
  icon: Icon,
  value,
  label,
  warn,
}: {
  icon: React.ElementType;
  value: number;
  label: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-mono font-medium ${
        warn
          ? "bg-red-500/10 text-red-400"
          : "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]"
      }`}
    >
      <Icon size={10} />
      <span>{label}:{value}</span>
    </div>
  );
}
