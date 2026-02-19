"use client";

interface Props {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}

export default function MetricTile({ icon: Icon, label, value, color }: Props) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={`p-1.5 rounded-md ${color}`}>
          <Icon size={14} />
        </div>
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium">
          {label}
        </span>
      </div>
      <p className="text-2xl font-bold tabular-nums font-mono">{value}</p>
    </div>
  );
}
