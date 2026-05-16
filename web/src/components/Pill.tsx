import clsx from "clsx";
import type { ReactNode } from "react";

type Props = {
  tone?: "default" | "pos" | "neg" | "yes" | "no" | "muted";
  children: ReactNode;
  className?: string;
};

export function Pill({ tone = "default", children, className }: Props) {
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium tabular border",
        tone === "default" && "border-line bg-bg-subtle text-ink-muted",
        tone === "muted" && "border-line/50 bg-transparent text-ink-dim",
        tone === "pos" && "border-pos/30 bg-pos/10 text-pos",
        tone === "neg" && "border-neg/30 bg-neg/10 text-neg",
        tone === "yes" && "border-pos/30 bg-pos/10 text-pos",
        tone === "no" && "border-neg/30 bg-neg/10 text-neg",
        className
      )}
    >
      {children}
    </span>
  );
}
