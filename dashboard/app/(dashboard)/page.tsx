"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers, Inbox, Zap, DollarSign, Power, Play } from "lucide-react";
import MetricTile from "@/components/cards/MetricTile";
import DecisionCard from "@/components/cards/DecisionCard";
import EditModal from "@/components/EditModal";
import DraftRefineModal from "@/components/DraftRefineModal";
import EmptyState from "@/components/EmptyState";
import CategoryBadge from "@/components/ui/CategoryBadge";
import type { AgentStatus, Draft, AgentEvent, DlqEntry, AgentAction } from "@/lib/types";
import { getCategory, timeAgo } from "@/lib/types";

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

export default function CommandCenter() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [dlq, setDlq] = useState<DlqEntry[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [editingDraft, setEditingDraft] = useState<Draft | null>(null);
  const [refiningDraftId, setRefiningDraftId] = useState<number | null>(null);

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
                  label: "Review & Send",
                  variant: "primary",
                  onClick: async () => setRefiningDraftId(d.id),
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

      {/* Refine & Send Modal */}
      {refiningDraftId !== null && (
        <DraftRefineModal
          draftId={refiningDraftId}
          onClose={() => setRefiningDraftId(null)}
          onSent={() => {
            setDrafts((prev) => prev.filter((x) => x.id !== refiningDraftId));
            setRefiningDraftId(null);
          }}
        />
      )}

      {/* Edit Modal (manual editing fallback) */}
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
