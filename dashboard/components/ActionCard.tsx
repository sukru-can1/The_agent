"use client";

import { useState } from "react";
import {
  Mail,
  AlertTriangle,
  HelpCircle,
  Info,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import clsx from "clsx";

type CardType = "draft" | "alert" | "question" | "info" | "error";
type Priority = "critical" | "high" | "medium" | "low";

interface Action {
  label: string;
  variant: "primary" | "secondary" | "danger";
  onClick: () => Promise<void> | void;
}

interface Props {
  type: CardType;
  title: string;
  subtitle?: string;
  body: string;
  priority: Priority;
  timestamp: string;
  actions: Action[];
  meta?: Record<string, string>;
  index?: number;
}

const typeConfig: Record<
  CardType,
  { icon: React.ElementType; accent: string; badge: string }
> = {
  draft: {
    icon: Mail,
    accent: "border-l-indigo-500",
    badge: "bg-indigo-500/10 text-indigo-400",
  },
  alert: {
    icon: AlertTriangle,
    accent: "border-l-amber-500",
    badge: "bg-amber-500/10 text-amber-400",
  },
  question: {
    icon: HelpCircle,
    accent: "border-l-purple-500",
    badge: "bg-purple-500/10 text-purple-400",
  },
  info: {
    icon: Info,
    accent: "border-l-sky-500",
    badge: "bg-sky-500/10 text-sky-400",
  },
  error: {
    icon: XCircle,
    accent: "border-l-red-500",
    badge: "bg-red-500/10 text-red-400",
  },
};

const priorityConfig: Record<Priority, { dot: string; label: string }> = {
  critical: { dot: "bg-red-500", label: "Critical" },
  high: { dot: "bg-amber-500", label: "High" },
  medium: { dot: "bg-sky-500", label: "Medium" },
  low: { dot: "bg-slate-500", label: "Low" },
};

const btnVariants = {
  primary:
    "bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white shadow-lg shadow-indigo-500/10",
  secondary:
    "bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)]",
  danger:
    "bg-red-500/10 hover:bg-red-500/20 text-red-400",
};

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ActionCard({
  type,
  title,
  subtitle,
  body,
  priority,
  timestamp,
  actions,
  meta,
  index = 0,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const cfg = typeConfig[type];
  const pri = priorityConfig[priority];
  const Icon = cfg.icon;

  if (dismissed) return null;

  const bodyPreview = body.length > 200 && !expanded ? body.slice(0, 200) + "..." : body;

  return (
    <div
      className={clsx(
        "card-enter rounded-2xl border-l-4 bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden transition-all hover:border-[var(--color-border-hover)]",
        cfg.accent,
        priority === "critical" && "pulse-critical"
      )}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Header */}
      <div className="px-5 pt-4 pb-2 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className={clsx("p-2 rounded-xl mt-0.5", cfg.badge)}>
            <Icon size={16} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
                {type}
              </span>
              <span className="flex items-center gap-1">
                <span className={clsx("w-1.5 h-1.5 rounded-full", pri.dot)} />
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  {pri.label}
                </span>
              </span>
            </div>
            <h3 className="font-semibold text-[15px] mt-0.5 leading-snug">{title}</h3>
            {subtitle && (
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-[var(--color-text-dim)] flex items-center gap-1">
            <Clock size={11} />
            {timeAgo(timestamp)}
          </span>
        </div>
      </div>

      {/* Meta pills */}
      {meta && Object.keys(meta).length > 0 && (
        <div className="px-5 pb-1 flex gap-1.5 flex-wrap">
          {Object.entries(meta).map(([k, v]) => (
            <span
              key={k}
              className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-text-muted)]"
            >
              {k}: {v}
            </span>
          ))}
        </div>
      )}

      {/* Body */}
      <div className="px-5 py-3">
        <div className="text-sm text-[var(--color-text-muted)] leading-relaxed whitespace-pre-wrap font-mono bg-[var(--color-bg)] rounded-xl p-4 border border-[var(--color-border)]">
          {bodyPreview}
        </div>
        {body.length > 200 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-[var(--color-accent)] mt-2 hover:underline"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
      </div>

      {/* Actions */}
      {actions.length > 0 && (
        <div className="px-5 pb-4 flex gap-2">
          {actions.map((action) => (
            <button
              key={action.label}
              disabled={loading !== null}
              onClick={async () => {
                setLoading(action.label);
                try {
                  await action.onClick();
                  setDismissed(true);
                } finally {
                  setLoading(null);
                }
              }}
              className={clsx(
                "px-4 py-2 rounded-xl text-sm font-medium transition-all btn-press",
                btnVariants[action.variant],
                loading === action.label && "opacity-60 cursor-wait",
                loading !== null && loading !== action.label && "opacity-40"
              )}
            >
              {loading === action.label ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  {action.label}
                </span>
              ) : (
                action.label
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
