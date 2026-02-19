"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useSession, signOut } from "next-auth/react";
import {
  LayoutDashboard,
  Activity,
  Brain,
  BarChart3,
  Settings,
  Pause,
  Play,
  LogOut,
} from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { pauseQueue, resumeQueue } from "@/lib/api";

const nav = [
  { href: "/", icon: LayoutDashboard, label: "Command Center" },
  { href: "/activity", icon: Activity, label: "Activity" },
  { href: "/knowledge", icon: Brain, label: "Knowledge" },
  { href: "/analytics", icon: BarChart3, label: "Analytics" },
  { href: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [paused, setPaused] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[var(--sidebar-width)] bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col items-center z-50">
      {/* Logo */}
      <div className="py-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">
          A
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 flex flex-col items-center gap-1 py-2">
        {nav.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            title={label}
            className={clsx(
              "w-10 h-10 flex items-center justify-center rounded-lg transition-colors",
              isActive(href)
                ? "sidebar-active bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                : "text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            )}
          >
            <Icon size={18} />
          </Link>
        ))}
      </nav>

      {/* Bottom controls */}
      <div className="flex flex-col items-center gap-1 pb-3">
        <button
          onClick={async () => {
            if (paused) {
              await resumeQueue();
              setPaused(false);
            } else {
              await pauseQueue();
              setPaused(true);
            }
          }}
          title={paused ? "Resume queue" : "Pause queue"}
          className={clsx(
            "w-10 h-10 flex items-center justify-center rounded-lg transition-colors",
            paused
              ? "text-amber-400 bg-amber-500/10"
              : "text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
          )}
        >
          {paused ? <Play size={16} /> : <Pause size={16} />}
        </button>

        {session?.user?.image && (
          <img
            src={session.user.image}
            alt=""
            className="w-7 h-7 rounded-full mt-1"
            referrerPolicy="no-referrer"
          />
        )}

        <button
          onClick={() => signOut()}
          title="Sign out"
          className="w-10 h-10 flex items-center justify-center rounded-lg text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] transition-colors"
        >
          <LogOut size={14} />
        </button>
      </div>
    </aside>
  );
}
