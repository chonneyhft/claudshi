export function fmtDollars(cents: number, opts: { sign?: boolean } = {}): string {
  const v = cents / 100;
  if (opts.sign) {
    const s = v >= 0 ? "+" : "";
    return `${s}$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtCents(cents: number): string {
  return `${cents}¢`;
}

export function fmtPct(p: number, sign = true): string {
  const s = sign && p > 0 ? "+" : "";
  return `${s}${p.toFixed(2)}%`;
}

export function fmtRelTime(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortTicker(ticker: string): string {
  return ticker.length > 20 ? ticker.slice(0, 20) + "…" : ticker;
}
