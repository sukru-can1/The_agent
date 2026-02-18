"use client";

import { CheckCircle2, Coffee } from "lucide-react";

const messages = [
  "All clear. Atlas is handling things.",
  "Nothing pending. Grab a coffee.",
  "Queue empty. Atlas is on watch.",
  "All caught up. Nice work, boss.",
  "Zero items. Atlas has it covered.",
];

export default function EmptyState() {
  const msg = messages[Math.floor(Math.random() * messages.length)];

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center card-enter">
      <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 flex items-center justify-center mb-6">
        <CheckCircle2 size={36} className="text-emerald-400" />
      </div>
      <p className="text-lg font-medium text-[var(--color-text)]">{msg}</p>
      <p className="text-sm text-[var(--color-text-dim)] mt-2 flex items-center gap-1.5">
        <Coffee size={14} />
        Checking every 30 seconds
      </p>
    </div>
  );
}
