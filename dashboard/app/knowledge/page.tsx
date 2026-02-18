"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, BookOpen, Brain, Tag, Clock } from "lucide-react";
import Link from "next/link";

interface KnowledgeEntry {
  id: number;
  category: string;
  content: string;
  source: string;
  created_at: string;
  active: boolean;
  confidence: number;
  supersedes_id: number | null;
}

const categoryColors: Record<string, string> = {
  taught_rule: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  edit_pattern: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  incident_resolution: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  escalation_rule: "bg-red-500/10 text-red-400 border-red-500/20",
  vip_customer: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  market_knowledge: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function KnowledgePage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/knowledge?limit=100");
      if (res.ok) {
        setEntries(await res.json());
      }
    } catch {
      // API not available
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const categories = Array.from(new Set(entries.map((e) => e.category)));
  const filtered =
    filter === "all" ? entries : entries.filter((e) => e.category === filter);

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
            <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400">
              <Brain size={20} />
            </div>
            <div>
              <h1 className="font-bold text-base">Knowledge Base</h1>
              <p className="text-[11px] text-[var(--color-text-muted)]">
                {entries.length} learned rules and patterns
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Filter bar */}
        <div className="flex items-center gap-2 mb-6 flex-wrap">
          <button
            onClick={() => setFilter("all")}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-colors ${
              filter === "all"
                ? "bg-indigo-500/20 text-indigo-400"
                : "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
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
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-colors ${
                  filter === cat
                    ? "bg-indigo-500/20 text-indigo-400"
                    : "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]"
                }`}
              >
                {cat.replace(/_/g, " ")} ({count})
              </button>
            );
          })}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
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
          <div className="space-y-3">
            {filtered.map((entry) => {
              const colorClass =
                categoryColors[entry.category] ||
                "bg-gray-500/10 text-gray-400 border-gray-500/20";
              return (
                <div
                  key={entry.id}
                  className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 card-enter"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-medium border ${colorClass}`}
                        >
                          <Tag size={10} />
                          {entry.category.replace(/_/g, " ")}
                        </span>
                        {entry.confidence < 1.0 && (
                          <span className="text-[10px] text-[var(--color-text-dim)]">
                            {(entry.confidence * 100).toFixed(0)}% conf
                          </span>
                        )}
                      </div>
                      <p className="text-sm leading-relaxed">{entry.content}</p>
                      <div className="flex items-center gap-4 mt-3 text-[10px] text-[var(--color-text-dim)]">
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
      </main>
    </div>
  );
}
