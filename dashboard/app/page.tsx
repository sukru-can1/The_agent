"use client";

import { useCallback, useEffect, useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";
import StatusBar from "@/components/StatusBar";
import ActionCard from "@/components/ActionCard";
import EditModal from "@/components/EditModal";
import EmptyState from "@/components/EmptyState";
import type { AgentStatus, Draft, AgentEvent, DlqEntry } from "@/lib/types";

// --- Demo data for when the API is not running ---
const DEMO_STATUS: AgentStatus = {
  queue_depth: 3,
  pending_drafts: 2,
  dlq_count: 1,
  last_action: {
    timestamp: new Date().toISOString(),
    system: "gmail",
    action_type: "email_drafted",
  },
};

const DEMO_DRAFTS: Draft[] = [
  {
    id: 1,
    gmail_message_id: "msg_001",
    from_address: "schmidt@dhl.com",
    to_address: "sukru@glamira.com",
    subject: "Re: Delivery delay — Order #GL-2024-8847 (Germany)",
    draft_body:
      'Dear Mr. Schmidt,\n\nThank you for your message regarding the delayed delivery of order #GL-2024-8847.\n\nI understand the customer is waiting for their engagement ring and this is time-sensitive. I\'ve checked our tracking system and the package appears to be held at the Hamburg sorting facility since Feb 15.\n\nCould you please escalate this to your priority handling team? The customer has been waiting 12 days past the estimated delivery date.\n\nBest regards,\nSukru Can\nCOO, GLAMIRA Group',
    status: "pending",
    classification: "urgent",
    created_at: new Date(Date.now() - 4 * 60000).toISOString(),
  },
  {
    id: 2,
    gmail_message_id: "msg_002",
    from_address: "maria@glamira.de",
    to_address: "sukru@glamira.com",
    subject: "Q4 Sales Report — Final Numbers",
    draft_body:
      "[via AGENT1] Hi Maria,\n\nThanks for sending the final Q4 numbers. I'll review them this afternoon and follow up with any questions.\n\nBest,\nSukru",
    status: "pending",
    classification: "fyi",
    created_at: new Date(Date.now() - 12 * 60000).toISOString(),
  },
];

const DEMO_EVENTS: AgentEvent[] = [
  {
    id: "evt-001",
    source: "freshdesk",
    event_type: "pattern_detected",
    priority: 1,
    status: "pending",
    created_at: new Date(Date.now() - 2 * 60000).toISOString(),
    error: null,
  },
  {
    id: "evt-002",
    source: "feedbacks",
    event_type: "trustpilot_review",
    priority: 3,
    status: "pending",
    created_at: new Date(Date.now() - 8 * 60000).toISOString(),
    error: null,
  },
  {
    id: "evt-003",
    source: "scheduler",
    event_type: "morning_brief",
    priority: 7,
    status: "pending",
    created_at: new Date(Date.now() - 20 * 60000).toISOString(),
    error: null,
  },
];

const DEMO_DLQ: DlqEntry[] = [
  {
    id: "dlq-001",
    original_event_id: "evt-999",
    source: "gmail",
    event_type: "new_email",
    priority: 5,
    error_history: [
      { retry: 1, error: "Connection timeout" },
      { retry: 2, error: "Connection timeout" },
      { retry: 3, error: "Connection timeout" },
    ],
    retry_count: 3,
    created_at: new Date(Date.now() - 45 * 60000).toISOString(),
  },
];

// --- Priority helpers ---
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

// --- Source emoji ---
const sourceIcon: Record<string, string> = {
  gmail: "✉️",
  freshdesk: "🎫",
  gchat: "💬",
  feedbacks: "📊",
  starinfinity: "⭐",
  scheduler: "⏰",
};

export default function Home() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [dlq, setDlq] = useState<DlqEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [useDemo, setUseDemo] = useState(false);
  const [paused, setPaused] = useState(false);
  const [editingDraft, setEditingDraft] = useState<Draft | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [statusRes, draftsRes, eventsRes, dlqRes] = await Promise.all([
        fetch("/api/admin/status"),
        fetch("/api/admin/drafts?status=pending"),
        fetch("/api/admin/events?status=pending&limit=20"),
        fetch("/api/admin/dlq"),
      ]);

      if (statusRes.ok) {
        setStatus(await statusRes.json());
        setDrafts(await draftsRes.json());
        setEvents(await eventsRes.json());
        setDlq(await dlqRes.json());
        setConnected(true);
        setUseDemo(false);
        return;
      }
    } catch {
      // API not available — use demo data
    }

    setStatus(DEMO_STATUS);
    setDrafts(DEMO_DRAFTS);
    setEvents(DEMO_EVENTS);
    setDlq(DEMO_DLQ);
    setUseDemo(true);
    setConnected(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchAll();
    setTimeout(() => setRefreshing(false), 500);
  };

  // Build card list
  const cards: React.ReactNode[] = [];

  // Drafts → cards
  drafts.forEach((d, i) => {
    cards.push(
      <ActionCard
        key={`draft-${d.id}`}
        type="draft"
        title={d.subject || "No subject"}
        subtitle={`From: ${d.from_address}`}
        body={d.draft_body}
        priority={classificationToPriority(d.classification)}
        timestamp={d.created_at}
        index={i}
        meta={{
          classification: d.classification,
          ...(d.to_address ? { to: d.to_address } : {}),
        }}
        actions={[
          {
            label: "Approve",
            variant: "primary",
            onClick: async () => {
              if (!useDemo) {
                await fetch(`/api/admin/drafts/${d.id}/approve`, {
                  method: "POST",
                });
              }
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
              if (!useDemo) {
                await fetch(`/api/admin/drafts/${d.id}/reject`, {
                  method: "POST",
                });
              }
              setDrafts((prev) => prev.filter((x) => x.id !== d.id));
            },
          },
        ]}
      />
    );
  });

  // Alert events → cards
  events
    .filter((e) => e.priority <= 3)
    .forEach((e, i) => {
      cards.push(
        <ActionCard
          key={`alert-${e.id}`}
          type="alert"
          title={`${sourceIcon[e.source] || "📌"} ${e.event_type.replace(/_/g, " ")}`}
          subtitle={`Source: ${e.source}`}
          body={`Priority ${e.priority} event from ${e.source}. Type: ${e.event_type}.${e.error ? `\n\nError: ${e.error}` : ""}`}
          priority={priorityLabel(e.priority)}
          timestamp={e.created_at}
          index={drafts.length + i}
          meta={{ source: e.source, id: e.id.slice(0, 8) }}
          actions={[
            {
              label: "Escalate",
              variant: "primary",
              onClick: async () => {
                setEvents((prev) => prev.filter((x) => x.id !== e.id));
              },
            },
            {
              label: "Dismiss",
              variant: "secondary",
              onClick: async () => {
                setEvents((prev) => prev.filter((x) => x.id !== e.id));
              },
            },
          ]}
        />
      );
    });

  // Info events → cards
  events
    .filter((e) => e.priority > 3)
    .forEach((e, i) => {
      cards.push(
        <ActionCard
          key={`info-${e.id}`}
          type="info"
          title={`${sourceIcon[e.source] || "📌"} ${e.event_type.replace(/_/g, " ")}`}
          body={`Routine ${e.source} event: ${e.event_type}`}
          priority={priorityLabel(e.priority)}
          timestamp={e.created_at}
          index={drafts.length + events.filter((x) => x.priority <= 3).length + i}
          actions={[
            {
              label: "OK",
              variant: "secondary",
              onClick: async () => {
                setEvents((prev) => prev.filter((x) => x.id !== e.id));
              },
            },
          ]}
        />
      );
    });

  // DLQ → error cards
  dlq.forEach((d, i) => {
    const lastError =
      d.error_history.length > 0
        ? d.error_history[d.error_history.length - 1].error
        : "Unknown error";
    cards.push(
      <ActionCard
        key={`dlq-${d.id}`}
        type="error"
        title={`Failed: ${d.event_type.replace(/_/g, " ")}`}
        subtitle={`${d.retry_count} retries exhausted`}
        body={`Source: ${d.source}\nLast error: ${lastError}\n\nRetried ${d.retry_count} times before moving to dead-letter queue.`}
        priority="high"
        timestamp={d.created_at}
        index={drafts.length + events.length + i}
        meta={{ source: d.source, retries: String(d.retry_count) }}
        actions={[
          {
            label: "Retry",
            variant: "primary",
            onClick: async () => {
              if (!useDemo) {
                await fetch(`/api/admin/dlq/${d.id}/retry`, { method: "POST" });
              }
              setDlq((prev) => prev.filter((x) => x.id !== d.id));
            },
          },
          {
            label: "Resolve",
            variant: "secondary",
            onClick: async () => {
              if (!useDemo) {
                await fetch(`/api/admin/dlq/${d.id}/resolve`, {
                  method: "POST",
                });
              }
              setDlq((prev) => prev.filter((x) => x.id !== d.id));
            },
          },
        ]}
      />
    );
  });

  return (
    <div className="min-h-screen">
      <StatusBar status={status} connected={connected} />

      {/* Toolbar */}
      <div className="max-w-4xl mx-auto px-4 pt-5 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
            {cards.length} pending
          </h2>
          {useDemo && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-medium">
              Demo Mode
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            className="p-2 rounded-xl hover:bg-[var(--color-surface-hover)] transition-colors"
            title="Refresh"
          >
            <RefreshCw
              size={16}
              className={`text-[var(--color-text-muted)] ${refreshing ? "animate-spin" : ""}`}
            />
          </button>
          <button
            onClick={async () => {
              if (paused) {
                if (!useDemo) await fetch("/api/admin/queue/resume", { method: "POST" });
                setPaused(false);
              } else {
                if (!useDemo) await fetch("/api/admin/queue/pause", { method: "POST" });
                setPaused(true);
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all btn-press ${
              paused
                ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                : "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
            }`}
          >
            {paused ? <Play size={12} /> : <Pause size={12} />}
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
      </div>

      {/* Card Stream */}
      <main className="max-w-4xl mx-auto px-4 pb-12 space-y-4">
        {cards.length > 0 ? cards : <EmptyState />}
      </main>

      {/* Edit Modal */}
      {editingDraft && (
        <EditModal
          title={editingDraft.subject}
          subtitle={`To: ${editingDraft.from_address}`}
          originalBody={editingDraft.draft_body}
          onClose={() => setEditingDraft(null)}
          onSave={async (edited) => {
            if (!useDemo) {
              await fetch(`/api/admin/drafts/${editingDraft.id}/approve`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ edited_body: edited }),
              });
            }
            setDrafts((prev) => prev.filter((x) => x.id !== editingDraft.id));
            setEditingDraft(null);
          }}
        />
      )}
    </div>
  );
}
