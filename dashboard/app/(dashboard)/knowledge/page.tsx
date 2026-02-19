"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Tag, Clock, Plus, X } from "lucide-react";
import type { KnowledgeEntry } from "@/lib/types";
import { timeAgo } from "@/lib/types";
import { storeKnowledge } from "@/lib/api";

const categoryColors: Record<string, string> = {
  taught_rule: "text-purple-400 bg-purple-500/10",
  edit_pattern: "text-amber-400 bg-amber-500/10",
  incident_resolution: "text-blue-400 bg-blue-500/10",
  escalation_rule: "text-red-400 bg-red-500/10",
  vip_customer: "text-emerald-400 bg-emerald-500/10",
  market_knowledge: "text-indigo-400 bg-indigo-500/10",
  operator_instruction: "text-cyan-400 bg-cyan-500/10",
};

export default function KnowledgePage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [showTeach, setShowTeach] = useState(false);
  const [teachContent, setTeachContent] = useState("");
  const [teaching, setTeaching] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/knowledge?limit=100");
      if (res.ok) setEntries(await res.json());
    } catch {
      // API not available
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleTeach = async () => {
    if (!teachContent.trim()) return;
    setTeaching(true);
    await storeKnowledge(teachContent, "operator_instruction");
    setTeachContent("");
    setShowTeach(false);
    setTeaching(false);
    fetchData();
  };

  const categories = Array.from(new Set(entries.map((e) => e.category)));
  const filtered = filter === "all" ? entries : entries.filter((e) => e.category === filter);

  return (
    <div className="space-y-4 max-w-5xl">
      {/* Filter bar + teach button */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setFilter("all")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === "all"
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            All ({entries.length})
          </button>
          {categories.map((cat) => {
            const count = entries.filter((e) => e.category === cat).length;
            return (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filter === cat
                    ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                    : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {cat.replace(/_/g, " ")} ({count})
              </button>
            );
          })}
        </div>
        <button
          onClick={() => setShowTeach(!showTeach)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-all btn-press"
        >
          {showTeach ? <X size={12} /> : <Plus size={12} />}
          Teach Agent
        </button>
      </div>

      {/* Teach input */}
      {showTeach && (
        <div className="rounded-lg border border-[var(--color-accent)]/30 bg-[var(--color-surface)] p-4 card-enter">
          <p className="text-xs text-[var(--color-text-muted)] mb-2">
            Write an instruction or rule for the agent to remember:
          </p>
          <textarea
            value={teachContent}
            onChange={(e) => setTeachContent(e.target.value)}
            rows={3}
            className="w-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-3 text-sm font-mono leading-relaxed resize-none focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            placeholder="e.g. Always escalate DHL delays over 7 days to their priority team..."
            autoFocus
          />
          <div className="flex justify-end mt-2">
            <button
              onClick={handleTeach}
              disabled={!teachContent.trim() || teaching}
              className="px-4 py-1.5 rounded-md text-xs font-medium bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-all btn-press disabled:opacity-40"
            >
              {teaching ? "Storing..." : "Store as Knowledge"}
            </button>
          </div>
        </div>
      )}

      {/* Entries */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-[var(--color-text-muted)]">
          <BookOpen size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium">No knowledge entries yet</p>
          <p className="text-sm mt-1">
            The agent learns from teachable rules and draft edits over time.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((entry) => {
            const colorClass =
              categoryColors[entry.category] || "text-gray-400 bg-gray-500/10";
            return (
              <div
                key={entry.id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 card-enter"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${colorClass}`}
                      >
                        <Tag size={10} />
                        {entry.category.replace(/_/g, " ")}
                      </span>
                      {entry.confidence < 1.0 && (
                        <span className="text-[10px] text-[var(--color-text-dim)] font-mono">
                          {(entry.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <p className="text-sm leading-relaxed">{entry.content}</p>
                    <div className="flex items-center gap-4 mt-2 text-[10px] text-[var(--color-text-dim)]">
                      <span className="flex items-center gap-1">
                        <BookOpen size={10} />
                        {entry.source}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock size={10} />
                        {timeAgo(entry.created_at)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
