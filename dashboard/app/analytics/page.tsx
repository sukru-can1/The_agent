"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  DollarSign,
  Clock,
  CheckCircle,
  TrendingUp,
  Zap,
  AlertTriangle,
  BarChart3,
} from "lucide-react";
import Link from "next/link";

interface DailyCost {
  day: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

interface ApprovalData {
  daily: Array<{
    day: string;
    approved: number;
    rejected: number;
    pending: number;
    sent: number;
  }>;
  edit_rate: { edited: number; total: number; ratio: number };
}

interface ResponseTime {
  day: string;
  system: string;
  count: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  p95_latency_ms: number | null;
}

interface Summary {
  events: { today: number; this_week: number };
  drafts: { pending: number; sent_this_week: number };
  errors: { failed_today: number; dlq_unresolved: number };
  tokens_today: { input: number; output: number };
  top_event_types: Array<{ event_type: string; source: string; count: number }>;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-xl ${color}`}>
          <Icon size={18} />
        </div>
        <p className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium">
          {label}
        </p>
      </div>
      <p className="text-3xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-[var(--color-text-muted)] mt-1">{sub}</p>}
    </div>
  );
}

function BarRow({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const width = max > 0 ? Math.max((value / max) * 100, 2) : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-[var(--color-text-muted)] w-28 truncate">{label}</span>
      <div className="flex-1 bg-[var(--color-surface-hover)] rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="text-xs font-medium tabular-nums w-12 text-right">{value}</span>
    </div>
  );
}

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [costs, setCosts] = useState<DailyCost[]>([]);
  const [approvals, setApprovals] = useState<ApprovalData | null>(null);
  const [latency, setLatency] = useState<ResponseTime[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, costsRes, approvalRes, latencyRes] = await Promise.all([
        fetch("/api/admin/analytics/summary"),
        fetch("/api/admin/analytics/daily-costs?days=7"),
        fetch("/api/admin/analytics/approval-rate?days=7"),
        fetch("/api/admin/analytics/response-time?days=7"),
      ]);

      if (summaryRes.ok) {
        setSummary(await summaryRes.json());
        setCosts(await costsRes.json());
        setApprovals(await approvalRes.json());
        setLatency(await latencyRes.json());
      }
    } catch {
      // API not available
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Aggregate costs by day
  const costByDay = costs.reduce<Record<string, number>>((acc, c) => {
    acc[c.day] = (acc[c.day] || 0) + c.estimated_cost_usd;
    return acc;
  }, {});
  const totalCostWeek = Object.values(costByDay).reduce((a, b) => a + b, 0);

  // Aggregate costs by model
  const costByModel = costs.reduce<Record<string, { calls: number; cost: number }>>((acc, c) => {
    const key = c.model.split("-").slice(0, 2).join("-");
    if (!acc[key]) acc[key] = { calls: 0, cost: 0 };
    acc[key].calls += c.calls;
    acc[key].cost += c.estimated_cost_usd;
    return acc;
  }, {});

  // Average latency by system
  const latencyBySystem = latency.reduce<Record<string, { total: number; count: number }>>((acc, l) => {
    if (!acc[l.system]) acc[l.system] = { total: 0, count: 0 };
    acc[l.system].total += l.avg_latency_ms * l.count;
    acc[l.system].count += l.count;
    return acc;
  }, {});

  const maxEventCount = summary
    ? Math.max(...(summary.top_event_types.map((t) => t.count) || [1]))
    : 1;

  const sourceColors: Record<string, string> = {
    gmail: "bg-blue-500",
    freshdesk: "bg-amber-500",
    gchat: "bg-emerald-500",
    feedbacks: "bg-purple-500",
    starinfinity: "bg-pink-500",
    scheduler: "bg-indigo-500",
  };

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
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
              <BarChart3 size={20} />
            </div>
            <div>
              <h1 className="font-bold text-base">Analytics</h1>
              <p className="text-[11px] text-[var(--color-text-muted)]">
                7-day performance overview
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : !summary ? (
          <div className="text-center py-20 text-[var(--color-text-muted)]">
            <BarChart3 size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">No analytics data yet</p>
            <p className="text-sm mt-1">Analytics will appear once the agent starts processing events.</p>
          </div>
        ) : (
          <>
            {/* Summary Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                icon={Zap}
                label="Events Today"
                value={summary.events.today}
                sub={`${summary.events.this_week} this week`}
                color="bg-indigo-500/10 text-indigo-400"
              />
              <StatCard
                icon={CheckCircle}
                label="Drafts Sent"
                value={summary.drafts.sent_this_week}
                sub={`${summary.drafts.pending} pending`}
                color="bg-emerald-500/10 text-emerald-400"
              />
              <StatCard
                icon={DollarSign}
                label="Cost (7d)"
                value={`$${totalCostWeek.toFixed(2)}`}
                sub={`${Object.values(costByModel).reduce((a, b) => a + b.calls, 0)} API calls`}
                color="bg-amber-500/10 text-amber-400"
              />
              <StatCard
                icon={AlertTriangle}
                label="Errors"
                value={summary.errors.failed_today}
                sub={`${summary.errors.dlq_unresolved} in DLQ`}
                color={
                  summary.errors.failed_today > 0
                    ? "bg-red-500/10 text-red-400"
                    : "bg-emerald-500/10 text-emerald-400"
                }
              />
            </div>

            {/* Cost Breakdown + Approval Rate */}
            <div className="grid md:grid-cols-2 gap-6">
              {/* Cost by Model */}
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                <div className="flex items-center gap-2 mb-4">
                  <DollarSign size={16} className="text-amber-400" />
                  <h3 className="font-semibold text-sm">Cost by Model</h3>
                </div>
                <div className="space-y-3">
                  {Object.entries(costByModel).map(([model, data]) => (
                    <div key={model} className="flex items-center justify-between">
                      <span className="text-xs text-[var(--color-text-muted)]">{model}</span>
                      <div className="text-right">
                        <span className="text-sm font-semibold">${data.cost.toFixed(3)}</span>
                        <span className="text-[10px] text-[var(--color-text-muted)] ml-2">
                          {data.calls} calls
                        </span>
                      </div>
                    </div>
                  ))}
                  {Object.keys(costByModel).length === 0 && (
                    <p className="text-xs text-[var(--color-text-dim)]">No cost data yet</p>
                  )}
                </div>
              </div>

              {/* Approval Rate */}
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle size={16} className="text-emerald-400" />
                  <h3 className="font-semibold text-sm">Draft Approval</h3>
                </div>
                {approvals ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-6">
                      <div>
                        <p className="text-2xl font-bold">
                          {((1 - approvals.edit_rate.ratio) * 100).toFixed(0)}%
                        </p>
                        <p className="text-[10px] text-[var(--color-text-muted)]">
                          Approved without edits
                        </p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold">
                          {(approvals.edit_rate.ratio * 100).toFixed(0)}%
                        </p>
                        <p className="text-[10px] text-[var(--color-text-muted)]">Edit rate</p>
                      </div>
                    </div>
                    <div className="text-xs text-[var(--color-text-muted)]">
                      {approvals.edit_rate.edited} of {approvals.edit_rate.total} approved drafts
                      were edited
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-[var(--color-text-dim)]">No approval data yet</p>
                )}
              </div>
            </div>

            {/* Response Time + Top Events */}
            <div className="grid md:grid-cols-2 gap-6">
              {/* Response Time by System */}
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Clock size={16} className="text-blue-400" />
                  <h3 className="font-semibold text-sm">Avg Response Time</h3>
                </div>
                <div className="space-y-3">
                  {Object.entries(latencyBySystem)
                    .sort((a, b) => b[1].total / b[1].count - a[1].total / a[1].count)
                    .map(([system, data]) => {
                      const avg = data.total / data.count;
                      return (
                        <div key={system} className="flex items-center justify-between">
                          <span className="text-xs text-[var(--color-text-muted)]">{system}</span>
                          <div className="text-right">
                            <span className="text-sm font-semibold">
                              {avg > 1000 ? `${(avg / 1000).toFixed(1)}s` : `${avg.toFixed(0)}ms`}
                            </span>
                            <span className="text-[10px] text-[var(--color-text-muted)] ml-2">
                              {data.count} events
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  {Object.keys(latencyBySystem).length === 0 && (
                    <p className="text-xs text-[var(--color-text-dim)]">No latency data yet</p>
                  )}
                </div>
              </div>

              {/* Top Event Types */}
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp size={16} className="text-purple-400" />
                  <h3 className="font-semibold text-sm">Top Events (7d)</h3>
                </div>
                <div className="space-y-1">
                  {summary.top_event_types.map((t, i) => (
                    <BarRow
                      key={i}
                      label={`${t.source}/${t.event_type}`}
                      value={t.count}
                      max={maxEventCount}
                      color={sourceColors[t.source] || "bg-gray-500"}
                    />
                  ))}
                  {summary.top_event_types.length === 0 && (
                    <p className="text-xs text-[var(--color-text-dim)]">No events yet</p>
                  )}
                </div>
              </div>
            </div>

            {/* Tokens */}
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="flex items-center gap-2 mb-3">
                <Zap size={16} className="text-indigo-400" />
                <h3 className="font-semibold text-sm">Token Usage Today</h3>
              </div>
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-xl font-bold tabular-nums">
                    {(summary.tokens_today.input / 1000).toFixed(1)}K
                  </p>
                  <p className="text-[10px] text-[var(--color-text-muted)]">Input tokens</p>
                </div>
                <div>
                  <p className="text-xl font-bold tabular-nums">
                    {(summary.tokens_today.output / 1000).toFixed(1)}K
                  </p>
                  <p className="text-[10px] text-[var(--color-text-muted)]">Output tokens</p>
                </div>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
