"use client";

import { useCallback, useEffect, useState } from "react";
import { Lightbulb, Check, X, ChevronDown, ChevronRight, Code2, Clock } from "lucide-react";
import type { Proposal } from "@/lib/types";
import { PROPOSAL_TYPE_CONFIG, timeAgo } from "@/lib/types";

export default function ProposalsPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending" | "approved" | "rejected">("pending");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const fetchProposals = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/proposals?status=${filter}&limit=50`);
      if (res.ok) setProposals(await res.json());
    } catch {
      // API not available
    }
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    setLoading(true);
    fetchProposals();
    const interval = setInterval(fetchProposals, 15000);
    return () => clearInterval(interval);
  }, [fetchProposals]);

  const handleApprove = async (id: string) => {
    const res = await fetch(`/api/admin/proposals/${id}/approve`, { method: "POST" });
    if (res.ok) fetchProposals();
  };

  const handleReject = async (id: string) => {
    const res = await fetch(`/api/admin/proposals/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Rejected from dashboard" }),
    });
    if (res.ok) fetchProposals();
  };

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        {(["pending", "approved", "rejected"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === f
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : proposals.length === 0 ? (
        <p className="text-center text-[var(--color-text-muted)] py-20 text-sm">
          No {filter} proposals
        </p>
      ) : (
        <div className="space-y-2">
          {proposals.map((p) => {
            const typeConfig = PROPOSAL_TYPE_CONFIG[p.type] || { label: p.type, color: "text-[var(--color-text-muted)]" };
            const isExpanded = expandedIds.has(p.id);

            return (
              <div key={p.id} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
                <div
                  onClick={() => toggleExpand(p.id)}
                  className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0" />
                  ) : (
                    <ChevronRight size={14} className="text-[var(--color-text-dim)] shrink-0" />
                  )}

                  <Lightbulb size={14} className="text-amber-400 shrink-0" />

                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] ${typeConfig.color}`}>
                    {typeConfig.label}
                  </span>

                  <span className="flex-1 text-xs truncate">{p.title}</span>

                  <span className="text-[10px] text-[var(--color-text-dim)]">
                    {Math.round(p.confidence * 100)}%
                  </span>

                  <span className="text-[10px] text-[var(--color-text-dim)] font-mono flex items-center gap-1">
                    <Clock size={10} />
                    {timeAgo(p.created_at)}
                  </span>

                  {filter === "pending" && (
                    <div className="flex items-center gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleApprove(p.id)}
                        className="p-1.5 rounded hover:bg-emerald-500/20 text-emerald-400 transition-colors"
                        title="Approve"
                      >
                        <Check size={14} />
                      </button>
                      <button
                        onClick={() => handleReject(p.id)}
                        className="p-1.5 rounded hover:bg-red-500/20 text-red-400 transition-colors"
                        title="Reject"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <div className="px-4 py-3 border-t border-[var(--color-border)] space-y-2 text-xs">
                    <div>
                      <span className="text-[var(--color-text-muted)] font-medium">Description: </span>
                      <span className="whitespace-pre-wrap">{p.description}</span>
                    </div>

                    {p.evidence && (
                      <div>
                        <span className="text-[var(--color-text-muted)] font-medium">Evidence: </span>
                        <span className="text-[var(--color-text-dim)]">{p.evidence}</span>
                      </div>
                    )}

                    {p.code && (
                      <div>
                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] font-medium mb-1">
                          <Code2 size={12} />
                          Code:
                        </div>
                        <pre className="p-2 rounded bg-[var(--color-bg)] text-[10px] font-mono overflow-x-auto max-h-48">
                          {p.code}
                        </pre>
                      </div>
                    )}

                    {p.reviewed_by && (
                      <div className="text-[10px] text-[var(--color-text-dim)]">
                        Reviewed by {p.reviewed_by} {p.reviewed_at ? timeAgo(p.reviewed_at) : ""}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
