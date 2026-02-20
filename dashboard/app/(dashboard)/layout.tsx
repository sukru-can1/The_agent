"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/shell/Sidebar";
import Topbar from "@/components/shell/Topbar";
import ChatPanel from "@/components/ChatPanel";
import type { AgentStatus, Category } from "@/lib/types";

const pageTitles: Record<string, string> = {
  "/": "Command Center",
  "/activity": "Activity Feed",
  "/knowledge": "Knowledge Base",
  "/analytics": "Analytics",
  "/settings": "Settings",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeCategory, setActiveCategory] = useState<Category | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/status");
      if (res.ok) {
        setStatus(await res.json());
        setConnected(true);
        return;
      }
    } catch {
      // not connected
    }
    setConnected(false);
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchStatus();
    setRefreshKey((k) => k + 1);
    setTimeout(() => setRefreshing(false), 500);
  };

  const title = pageTitles[pathname] || "The Agent1";

  return (
    <div className="min-h-screen dot-grid">
      <Sidebar />
      <div className="ml-[var(--sidebar-width)]">
        <Topbar
          title={title}
          status={status}
          connected={connected}
          onRefresh={handleRefresh}
          refreshing={refreshing}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
        <main className="p-5" key={refreshKey}>
          {children}
        </main>
      </div>
      <ChatPanel />
    </div>
  );
}
