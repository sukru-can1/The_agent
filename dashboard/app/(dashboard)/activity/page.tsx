"use client";

import { useCallback, useEffect, useState } from "react";
import { Clock, Cpu, Zap, ChevronDown, ChevronRight, ExternalLink, Wrench } from "lucide-react";
import CategoryBadge from "@/components/ui/CategoryBadge";
import type { AgentEvent, AgentAction, Category } from "@/lib/types";
import { getCategory, extractDetail, extractActionSummary, timeAgo } from "@/lib/types";

type FeedItem =
  | { kind: "event"; data: AgentEvent; ts: string }
  | { kind: "action"; data: AgentAction; ts: string };

const outcomeColors: Record<string, string> = {
  success: "text-emerald-400",
  blocked: "text-amber-400",
  failed: "text-red-400",
};

function ActionExpandedRow({ action }: { action: AgentAction }) {
  const summary = extractActionSummary(action);

  return (
    <div className="px-4 py-3 bg-[var(--color-bg)] border-x border-b border-[var(--color-border)] rounded-b-md space-y-2 text-xs">
      {/* What */}
      {summary.eventSummary && (
        <div>
          <span className="text-[var(--color-text-muted)] font-medium">What: </span>
          <span>{summary.eventSummary}</span>
        </div>
      )}

      {/* Tools used */}
      {summary.toolsUsed.length > 0 && (
        <div className="flex items-start gap-1.5">
          <Wrench size={12} className="text-[var(--color-text-muted)] mt-0.5 shrink-0" />
          <div className="flex flex-wrap gap-1">
            {summary.toolsUsed.map((t, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] font-mono text-[10px]"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Agent response */}
      {summary.agentResponse && (
        <div>
          <span className="text-[var(--color-text-muted)] font-medium">Response: </span>
          <span className="text-[var(--color-text-muted)]">{summary.agentResponse}</span>
        </div>
      )}

      {/* Model + tokens + latency */}
      <div className="flex items-center gap-4 text-[10px] text-[var(--color-text-muted)]">
        {action.model_used && (
          <span className="flex items-center gap-1">
            <Cpu size={10} />
            {action.model_used}
          </span>
        )}
        {(action.input_tokens > 0 || action.output_tokens > 0) && (
          <span className="flex items-center gap-1">
            <Zap size={10} />
            {action.input_tokens.toLocaleString()} in / {action.output_tokens.toLocaleString()} out
          </span>
        )}
        {action.latency_ms > 0 && (
          <span>{(action.latency_ms / 1000).toFixed(1)}s</span>
        )}
      </div>

      {/* External link */}
      {summary.externalLink && (
        <a
          href={summary.externalLink}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[var(--color-accent)] hover:underline text-[11px]"
        >
          <ExternalLink size={11} />
          Open in {action.system}
        </a>
      )}
    </div>
  );
}

export default function ActivityPage() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "events" | "actions">("all");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const fetchData = useCallback(async () => {
    try {
      const [eventsRes, actionsRes] = await Promise.all([
        fetch("/api/admin/events?status=processed&limit=50"),
        fetch("/api/admin/actions?limit=100"),
      ]);
      if (eventsRes.ok) setEvents(await eventsRes.json());
      if (actionsRes.ok) setActions(await actionsRes.json());
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

  // Merge and sort
  const feed: FeedItem[] = [];
  if (filter !== "actions") {
    events.forEach((e) => feed.push({ kind: "event", data: e, ts: e.created_at }));
  }
  if (filter !== "events") {
    actions.forEach((a) => feed.push({ kind: "action", data: a, ts: a.timestamp }));
  }
  feed.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        {(["all", "events", "actions"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === f
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {f === "all" ? `All (${feed.length})` : f === "events" ? "Events" : "Actions"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : feed.length === 0 ? (
        <p className="text-center text-[var(--color-text-muted)] py-20 text-sm">
          No activity recorded yet
        </p>
      ) : (
        <div className="space-y-1">
          {feed.slice(0, 200).map((item, i) => {
            if (item.kind === "event") {
              const e = item.data;
              const detail = extractDetail(e.source, e.payload);
              return (
                <div
                  key={`e-${e.id}-${i}`}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-border-hover)] transition-colors"
                >
                  <CategoryBadge category={getCategory(e.source, e.event_type)} />
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
                    {e.source}
                  </span>
                  <span className="flex-1 text-xs truncate">
                    {e.event_type.replace(/_/g, " ")}
                    {detail && (
                      <span className="text-[var(--color-text-dim)] ml-1.5">{detail}</span>
                    )}
                  </span>
                  <span className="text-[10px] text-[var(--color-text-dim)] font-mono shrink-0 flex items-center gap-1">
                    <Clock size={10} />
                    {timeAgo(e.created_at)}
                  </span>
                </div>
              );
            }

            const a = item.data;
            const rowKey = `a-${a.id}`;
            const isExpanded = expandedIds.has(rowKey);

            return (
              <div key={`${rowKey}-${i}`}>
                <div
                  onClick={() => toggleExpand(rowKey)}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-border-hover)] transition-colors cursor-pointer select-none"
                >
                  {isExpanded ? (
                    <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0" />
                  ) : (
                    <ChevronRight size={14} className="text-[var(--color-text-dim)] shrink-0" />
                  )}
                  <CategoryBadge category={getCategory(a.system, a.action_type)} />
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
                    {a.system}
                  </span>
                  <span className="flex-1 text-xs truncate">
                    {a.action_type.replace(/_/g, " ")}
                  </span>

                  {a.model_used && (
                    <span className="hidden sm:flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
                      <Cpu size={10} />
                      {a.model_used.split("-").slice(0, 2).join("-")}
                    </span>
                  )}

                  {(a.input_tokens > 0 || a.output_tokens > 0) && (
                    <span className="hidden sm:flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
                      <Zap size={10} />
                      {((a.input_tokens + a.output_tokens) / 1000).toFixed(1)}K
                    </span>
                  )}

                  <span
                    className={`text-[10px] font-medium ${
                      outcomeColors[a.outcome] || "text-[var(--color-text-dim)]"
                    }`}
                  >
                    {a.outcome}
                  </span>

                  <span className="text-[10px] text-[var(--color-text-dim)] font-mono w-14 text-right shrink-0">
                    {timeAgo(a.timestamp)}
                  </span>
                </div>

                {isExpanded && <ActionExpandedRow action={a} />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
