import clsx from "clsx";
import { Link, useLocation } from "wouter";
import { motion } from "framer-motion";
import { usePortfolio } from "../lib/api";
import { fmtDollars, fmtPct } from "../lib/format";

const TABS = [
  { href: "/", label: "Portfolio" },
  { href: "/pnl", label: "P&L" },
  { href: "/trades", label: "Trades" },
  { href: "/sessions", label: "Sessions" },
];

export function Nav() {
  const [location] = useLocation();
  const { data } = usePortfolio();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-pos to-accent" />
            <span className="font-medium tracking-tight">claudshi</span>
          </Link>
          <nav className="flex items-center gap-1">
            {TABS.map((t) => {
              const active =
                location === t.href ||
                (t.href !== "/" && location.startsWith(t.href));
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  className={clsx(
                    "relative px-3 py-1.5 text-sm transition-colors",
                    active ? "text-ink" : "text-ink-muted hover:text-ink"
                  )}
                >
                  {active && (
                    <motion.div
                      layoutId="nav-pill"
                      className="absolute inset-0 bg-line/40 rounded-md"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <span className="relative">{t.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
        {data && (
          <div className="flex items-center gap-4 text-sm tabular">
            <div className="text-ink-muted">
              {fmtDollars(data.total_value.cents)}
            </div>
            <div
              className={clsx(
                "text-xs px-2 py-0.5 rounded border tabular",
                data.pct_return >= 0
                  ? "border-pos/30 bg-pos/10 text-pos"
                  : "border-neg/30 bg-neg/10 text-neg"
              )}
            >
              {fmtPct(data.pct_return)}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
