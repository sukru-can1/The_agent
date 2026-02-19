"use client";

import { Mail, MessageSquare, Headphones, Star, Database, Compass, BarChart3, Wrench } from "lucide-react";
import type { Integration } from "@/lib/types";

const iconMap: Record<string, React.ElementType> = {
  gmail: Mail,
  gchat: MessageSquare,
  freshdesk: Headphones,
  starinfinity: Star,
  feedbacks: Database,
  voyage: Compass,
  langfuse: BarChart3,
  mcp: Wrench,
};

const descMap: Record<string, string> = {
  gmail: "Email scanning and draft generation",
  gchat: "Google Chat space monitoring and responses",
  freshdesk: "Customer support ticket processing",
  starinfinity: "Project management board sync",
  feedbacks: "Customer feedback and review monitoring",
  voyage: "AI-powered semantic search embeddings",
  langfuse: "LLM observability and cost tracking",
  mcp: "Model Context Protocol dynamic tools",
};

export default function IntegrationCard({ integration }: { integration: Integration }) {
  const Icon = iconMap[integration.id] || Wrench;
  const desc = descMap[integration.id] || "External integration";

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 flex items-start gap-3">
      <div className="p-2 rounded-md bg-[var(--color-surface-hover)]">
        <Icon size={16} className="text-[var(--color-text-muted)]" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{integration.name}</h3>
          <span
            className={`w-2 h-2 rounded-full ${
              integration.active ? "bg-[var(--color-success)]" : "bg-[var(--color-text-dim)]"
            }`}
          />
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{desc}</p>
      </div>
      <span
        className={`text-[10px] font-medium px-2 py-0.5 rounded ${
          integration.active
            ? "bg-emerald-500/10 text-emerald-400"
            : "bg-[var(--color-surface-hover)] text-[var(--color-text-dim)]"
        }`}
      >
        {integration.active ? "Active" : "Not configured"}
      </span>
    </div>
  );
}
