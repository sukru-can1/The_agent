"use client";

import { useCallback, useEffect, useState } from "react";
import { Wrench, Send } from "lucide-react";
import IntegrationCard from "@/components/cards/IntegrationCard";
import type { Integration } from "@/lib/types";

interface ConfigEntry {
  key: string;
  value: string;
  updated_at: string;
  description: string | null;
}

export default function SettingsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [config, setConfig] = useState<ConfigEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [injectText, setInjectText] = useState("");
  const [injecting, setInjecting] = useState(false);
  const [injected, setInjected] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [intRes, cfgRes] = await Promise.all([
        fetch("/api/admin/integrations"),
        fetch("/api/admin/config"),
      ]);
      if (intRes.ok) setIntegrations(await intRes.json());
      if (cfgRes.ok) setConfig(await cfgRes.json());
    } catch {
      // API not available
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleInject = async () => {
    if (!injectText.trim()) return;
    setInjecting(true);
    try {
      await fetch("/api/admin/inject-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: "gchat", event_type: "chat_message", text: injectText }),
      });
      setInjected(true);
      setInjectText("");
      setTimeout(() => setInjected(false), 2000);
    } catch {
      // ignore
    }
    setInjecting(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Integrations */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          Integrations
        </h2>
        <div className="grid sm:grid-cols-2 gap-3">
          {integrations.map((int) => (
            <IntegrationCard key={int.id} integration={int} />
          ))}
          {integrations.length === 0 && (
            <p className="text-sm text-[var(--color-text-dim)] col-span-2">
              Unable to load integrations
            </p>
          )}
        </div>
      </section>

      {/* Runtime Config */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          Runtime Configuration
        </h2>
        {config.length > 0 ? (
          <div className="space-y-2">
            {config.map((c) => (
              <div
                key={c.key}
                className="flex items-center gap-4 px-4 py-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]"
              >
                <span className="text-xs font-mono font-medium text-[var(--color-text)] flex-shrink-0">
                  {c.key}
                </span>
                <span className="flex-1 text-xs text-[var(--color-text-muted)] font-mono truncate">
                  {typeof c.value === "string" ? c.value : JSON.stringify(c.value)}
                </span>
                {c.description && (
                  <span className="text-[10px] text-[var(--color-text-dim)] max-w-48 truncate">
                    {c.description}
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-dim)]">No runtime config entries</p>
        )}
      </section>

      {/* Inject Event */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          Inject Test Event
        </h2>
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
          <Wrench size={16} className="text-[var(--color-text-dim)] shrink-0" />
          <input
            type="text"
            value={injectText}
            onChange={(e) => setInjectText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleInject()}
            placeholder="Type a message to inject as a test event..."
            className="flex-1 bg-transparent text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] focus:outline-none"
            disabled={injecting}
          />
          <button
            onClick={handleInject}
            disabled={!injectText.trim() || injecting}
            className="px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-all btn-press disabled:opacity-40 flex items-center gap-1.5"
          >
            <Send size={12} />
            {injected ? "Sent!" : "Inject"}
          </button>
        </div>
      </section>
    </div>
  );
}
