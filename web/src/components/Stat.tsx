import clsx from "clsx";
import type { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "pos" | "neg" | "neutral";
  className?: string;
};

export function Stat({ label, value, sub, tone = "neutral", className }: Props) {
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <div className="text-[11px] uppercase tracking-wider text-ink-dim">
        {label}
      </div>
      <div
        className={clsx(
          "text-2xl font-medium tabular tracking-tight",
          tone === "pos" && "text-pos",
          tone === "neg" && "text-neg"
        )}
      >
        {value}
      </div>
      {sub && <div className="text-sm text-ink-muted tabular">{sub}</div>}
    </div>
  );
}
