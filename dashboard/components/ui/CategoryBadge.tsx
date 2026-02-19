"use client";

import { CATEGORY_CONFIG, type Category } from "@/lib/types";

export default function CategoryBadge({ category }: { category: Category }) {
  const cfg = CATEGORY_CONFIG[category];
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{
        color: cfg.color,
        backgroundColor: `${cfg.color}15`,
      }}
    >
      {cfg.label}
    </span>
  );
}
