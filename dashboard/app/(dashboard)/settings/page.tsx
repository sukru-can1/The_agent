"use client";

import { useCallback, useEffect, useState } from "react";
import { Wrench, Send, Cpu } from "lucide-react";
import IntegrationCard from "@/components/cards/IntegrationCard";
import type { Integration } from "@/lib/types";

interface ConfigEntry {
  key: string;
  value: string;
  updated_at: string;
  description: string | null;
}

interface LLMProviderInfo {
  provider: string;
  available: boolean;
  models: { flash: string; fast: string; default: string; pro: string };
}

export default function SettingsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [config, setConfig] = useState<ConfigEntry[]>([]);
  const [llmProvider, setLlmProvider] = useState<LLMProviderInfo | null>(null);
  const [switching, setSwitching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [injectText, setInjectText] = useState("");
  const [injecting, setInjecting] = useState(false);
  const [injected, setInjected] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [intRes, cfgRes, llmRes] = await Promise.all([
        fetch("/api/admin/integrations"),
        fetch("/api/admin/config"),
        fetch("/api/admin/llm-provider"),
      ]);
      if (intRes.ok) setIntegrations(await intRes.json());
      if (cfgRes.ok) setConfig(await cfgRes.json());
      if (llmRes.ok) setLlmProvider(await llmRes.json());
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

  const handleSwitchProvider = async (name: string) => {
    if (switching || name === llmProvider?.provider) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/admin/llm-provider", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: name }),
      });
      if (res.ok) {
        const llmRes = await fetch("/api/admin/llm-provider");
        if (llmRes.ok) setLlmProvider(await llmRes.json());
      } else {
        const err = await res.json().catch(() => ({ detail: "Switch failed" }));
        alert(err.detail || "Failed to switch provider");
      }
    } catch {
      // ignore
    }
    setSwitching(false);
  };

  return (
    <div className="space-y-8 max-w-4xl">
      {/* LLM Provider */}
      {llmProvider && (
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            LLM Provider
          </h2>
          <div className="p-4 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] space-y-4">
            <div className="flex items-center gap-3">
              <Cpu size={16} className="text-[var(--color-accent)] shrink-0" />
              <div className="flex gap-2">
                {["gemini", "openrouter"].map((p) => (
                  <button
                    key={p}
                    onClick={() => handleSwitchProvider(p)}
                    disabled={switching}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      llmProvider.provider === p
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] border border-[var(--color-border)]"
                    } disabled:opacity-40`}
                  >
                    {p === "gemini" ? "Google Gemini" : "OpenRouter"}
                  </button>
                ))}
              </div>
              {switching && (
                <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              )}
              <span className={`ml-auto text-[10px] font-medium ${llmProvider.available ? "text-emerald-400" : "text-red-400"}`}>
                {llmProvider.available ? "CONNECTED" : "NO API KEY"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(["flash", "fast", "default", "pro"] as const).map((tier) => (
                <div key={tier} className="flex items-center gap-2 px-3 py-2 rounded-md bg-[var(--color-bg)]">
                  <span className="text-[10px] uppercase font-semibold text-[var(--color-text-dim)] w-12">{tier}</span>
                  <span className="text-xs font-mono text-[var(--color-text-muted)] truncate">
                    {llmProvider.models[tier]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

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
