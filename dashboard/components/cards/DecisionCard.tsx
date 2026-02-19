"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Clock } from "lucide-react";
import clsx from "clsx";
import CategoryBadge from "@/components/ui/CategoryBadge";
import CommentInput from "@/components/ui/CommentInput";
import { type Category, extractDetail, timeAgo } from "@/lib/types";

type CardVariant = "draft" | "alert" | "dlq" | "info";
type Priority = "critical" | "high" | "medium" | "low";

interface Action {
  label: string;
  variant: "primary" | "secondary" | "danger";
  onClick: () => Promise<void> | void;
}

interface Props {
  variant: CardVariant;
  category: Category;
  title: string;
  subtitle?: string;
  detail?: string;
  body: string;
  priority: Priority;
  timestamp: string;
  source: string;
  payload?: Record<string, unknown> | null;
  actions: Action[];
}

const priorityDot: Record<Priority, string> = {
  critical: "bg-red-500",
  high: "bg-amber-500",
  medium: "bg-sky-500",
  low: "bg-slate-500",
};

const variantBorder: Record<CardVariant, string> = {
  draft: "border-l-indigo-500",
  alert: "border-l-amber-500",
  dlq: "border-l-red-500",
  info: "border-l-sky-500",
};

const btnStyles = {
  primary: "bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white",
  secondary: "bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)]",
  danger: "bg-red-500/10 hover:bg-red-500/20 text-red-400",
};

export default function DecisionCard({
  variant,
  category,
  title,
  subtitle,
  detail,
  body,
  priority,
  timestamp,
  source,
  payload,
  actions,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const richDetail = detail || extractDetail(source, payload ?? null);
  const bodyPreview = body.length > 180 && !expanded ? body.slice(0, 180) + "..." : body;

  return (
    <div
      className={clsx(
        "card-enter rounded-lg border-l-4 bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden transition-all hover:border-[var(--color-border-hover)]",
        variantBorder[variant],
        priority === "critical" && "pulse-critical"
      )}
    >
      {/* Header */}
      <div className="px-4 pt-3 pb-1 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <CategoryBadge category={category} />
          <div className="min-w-0">
            <h3 className="font-semibold text-sm leading-snug">{title}</h3>
            {subtitle && (
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={clsx("w-1.5 h-1.5 rounded-full", priorityDot[priority])} />
          <span className="text-[10px] text-[var(--color-text-dim)] flex items-center gap-1">
            <Clock size={10} />
            {timeAgo(timestamp)}
          </span>
        </div>
      </div>

      {/* Rich detail */}
      {richDetail && (
        <div className="px-4 pb-1">
          <p className="text-xs text-[var(--color-text-muted)] font-mono truncate">
            {richDetail}
          </p>
        </div>
      )}

      {/* Body */}
      <div className="px-4 py-2">
        <div className="text-xs text-[var(--color-text-muted)] leading-relaxed whitespace-pre-wrap font-mono bg-[var(--color-bg)] rounded-md p-3 border border-[var(--color-border)]">
          {bodyPreview}
        </div>
        {body.length > 180 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-[var(--color-accent)] mt-1.5 hover:underline"
          >
            {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            {expanded ? "Less" : "More"}
          </button>
        )}
      </div>

      {/* Actions */}
      {actions.length > 0 && (
        <div className="px-4 pb-2 flex gap-2">
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
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all btn-press",
                btnStyles[action.variant],
                loading === action.label && "opacity-60 cursor-wait",
                loading !== null && loading !== action.label && "opacity-40"
              )}
            >
              {loading === action.label ? (
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  {action.label}
                </span>
              ) : (
                action.label
              )}
            </button>
          ))}
        </div>
      )}

      {/* Comment input */}
      <div className="px-4 pb-3">
        <CommentInput context={title} />
      </div>
    </div>
  );
}
