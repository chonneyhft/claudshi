import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { useTrades } from "../lib/api";
import { fmtCents, fmtDollars, fmtDate } from "../lib/format";

export function TradesView() {
  const { data: trades } = useTrades();
  const [filter, setFilter] = useState<"all" | "buy" | "sell" | "settle">("all");
  const [openId, setOpenId] = useState<string | null>(null);

  if (!trades) return <div className="text-ink-muted">Loading…</div>;

  const filtered =
    filter === "all" ? trades : trades.filter((t) => t.action === filter);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 p-1 rounded-lg border border-line bg-bg-card">
          {(["all", "buy", "sell", "settle"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="relative px-3 py-1 text-xs uppercase tracking-wider"
            >
              {filter === f && (
                <motion.div
                  layoutId="trade-filter"
                  className="absolute inset-0 bg-line rounded-md"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
              <span
                className={
                  "relative " +
                  (filter === f ? "text-ink" : "text-ink-muted hover:text-ink")
                }
              >
                {f}
              </span>
            </button>
          ))}
        </div>
        <div className="text-xs text-ink-dim tabular">
          {filtered.length} of {trades.length}
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="divide-y divide-line/60">
          {filtered.map((t, i) => {
            const open = openId === t.id;
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i, 20) * 0.015 }}
                className="hover:bg-bg-subtle/40 transition-colors"
              >
                <button
                  className="w-full px-5 py-3 flex items-center gap-4 text-sm text-left"
                  onClick={() => setOpenId(open ? null : t.id)}
                >
                  <Pill
                    tone={
                      t.action === "buy"
                        ? "pos"
                        : t.action === "sell"
                          ? "neg"
                          : "muted"
                    }
                  >
                    {t.action}
                  </Pill>
                  <Pill tone={t.side === "yes" ? "yes" : "no"}>
                    {t.side.toUpperCase()}
                  </Pill>
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-xs text-ink truncate">
                      {t.ticker}
                    </div>
                    {t.market_title && (
                      <div className="text-xs text-ink-dim truncate">
                        {t.market_title}
                      </div>
                    )}
                  </div>
                  <span className="tabular text-ink-muted w-16 text-right">
                    ×{t.quantity}
                  </span>
                  <span className="tabular w-16 text-right">
                    {fmtCents(t.price_cents)}
                  </span>
                  <span className="tabular w-24 text-right">
                    {fmtDollars(t.total_cost_cents)}
                  </span>
                  <span className="text-xs text-ink-dim w-28 text-right">
                    {fmtDate(t.timestamp)}
                  </span>
                  <svg
                    className={
                      "w-3 h-3 text-ink-dim transition-transform " +
                      (open ? "rotate-180" : "")
                    }
                    viewBox="0 0 12 12"
                  >
                    <path
                      d="M3 5l3 3 3-3"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      fill="none"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
                <AnimatePresence initial={false}>
                  {open && t.reasoning && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-4 pt-1 text-sm text-ink-muted leading-relaxed whitespace-pre-wrap border-l-2 border-accent/40 ml-5 mr-5 mb-4 pl-4">
                        {t.reasoning}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
