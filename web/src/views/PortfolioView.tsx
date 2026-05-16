import { motion } from "framer-motion";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { Sparkline } from "../components/Sparkline";
import { Stat } from "../components/Stat";
import {
  usePortfolio,
  usePositions,
  useSnapshots,
  useTrades,
} from "../lib/api";
import { fmtCents, fmtDollars, fmtPct, fmtRelTime } from "../lib/format";

export function PortfolioView() {
  const { data: p } = usePortfolio();
  const { data: positions } = usePositions();
  const { data: snapshots } = useSnapshots();
  const { data: trades } = useTrades();

  if (!p) return <Loading />;

  const sparkData = (snapshots ?? []).map((s) => ({
    value: s.total_value_cents / 100,
  }));
  const positive = p.pct_return >= 0;

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-2 p-8">
          <div className="text-[11px] uppercase tracking-wider text-ink-dim mb-2">
            Portfolio value
          </div>
          <div className="flex items-baseline gap-4 mb-6">
            <div className="text-5xl font-medium tabular tracking-tight">
              <AnimatedNumber
                value={p.total_value.dollars}
                format={(v) =>
                  "$" +
                  v.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })
                }
              />
            </div>
            <Pill tone={positive ? "pos" : "neg"}>
              {fmtPct(p.pct_return)}
            </Pill>
            <div
              className={
                "text-base tabular " + (positive ? "text-pos" : "text-neg")
              }
            >
              {fmtDollars(p.total_pnl.cents, { sign: true })}
            </div>
          </div>
          {sparkData.length > 1 && (
            <div className="-mx-2">
              <Sparkline data={sparkData} positive={positive} height={80} />
            </div>
          )}
        </Card>

        <Card className="p-6 flex flex-col justify-between">
          <div className="space-y-4">
            <Stat
              label="Cash"
              value={fmtDollars(p.balance.cents)}
              sub={`of ${fmtDollars(p.starting_balance.cents)} starting`}
            />
            <div className="h-px bg-line/60" />
            <Stat
              label="Invested"
              value={fmtDollars(p.positions_value.cents)}
              sub={`${p.num_positions} positions`}
            />
            <div className="h-px bg-line/60" />
            <Stat
              label="Realized P&L"
              value={fmtDollars(p.realized_pnl.cents, { sign: true })}
              tone={p.realized_pnl.cents >= 0 ? "pos" : "neg"}
            />
          </div>
        </Card>
      </section>

      {/* Positions */}
      <section>
        <SectionHeader
          title="Open positions"
          count={positions?.length ?? 0}
        />
        {positions && positions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {positions.map((pos, i) => (
              <PositionCard key={pos.ticker} pos={pos} delay={i * 0.04} />
            ))}
          </div>
        ) : (
          <EmptyState>No open positions.</EmptyState>
        )}
      </section>

      {/* Recent trades */}
      <section>
        <SectionHeader title="Recent activity" />
        <Card className="divide-y divide-line/60">
          {(trades ?? []).slice(0, 8).map((t) => (
            <div
              key={t.id}
              className="px-5 py-3 flex items-center gap-4 text-sm"
            >
              <Pill tone={t.action === "buy" ? "pos" : t.action === "sell" ? "neg" : "muted"}>
                {t.action}
              </Pill>
              <Pill tone={t.side === "yes" ? "yes" : "no"}>
                {t.side.toUpperCase()}
              </Pill>
              <span className="font-mono text-xs text-ink-muted truncate flex-1">
                {t.ticker}
              </span>
              <span className="tabular text-ink-muted">×{t.quantity}</span>
              <span className="tabular w-16 text-right">
                {fmtCents(t.price_cents)}
              </span>
              <span className="tabular w-24 text-right">
                {fmtDollars(t.total_cost_cents)}
              </span>
              <span className="text-xs text-ink-dim w-20 text-right">
                {fmtRelTime(t.timestamp)}
              </span>
            </div>
          ))}
        </Card>
      </section>
    </div>
  );
}

function PositionCard({
  pos,
  delay,
}: {
  pos: import("../lib/api").Position;
  delay: number;
}) {
  const sideTone = pos.side === "yes" ? "yes" : "no";
  return (
    <Card hover delay={delay} className="p-5">
      <div className="flex items-start justify-between mb-3 gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Pill tone={sideTone}>{pos.side.toUpperCase()}</Pill>
            {pos.thesis?.category && (
              <Pill tone="muted">{pos.thesis.category}</Pill>
            )}
          </div>
          <div className="font-mono text-sm text-ink truncate">{pos.ticker}</div>
        </div>
        <div className="text-right">
          <div className="text-xl font-medium tabular">
            {fmtDollars(pos.cost_basis_cents)}
          </div>
          <div className="text-xs text-ink-dim tabular">
            ×{pos.quantity} @ {fmtCents(pos.avg_price_cents)}
          </div>
        </div>
      </div>

      {pos.thesis && (
        <>
          <div className="flex items-center gap-3 mb-3">
            <ProbBar
              estimate={pos.thesis.probability_estimate}
              entry={pos.thesis.market_price_at_entry}
              side={pos.side}
            />
          </div>
          <p className="text-xs text-ink-muted leading-relaxed line-clamp-3">
            {pos.thesis.entry_thesis}
          </p>
        </>
      )}

      <div className="mt-3 pt-3 border-t border-line/60 flex justify-between text-xs text-ink-dim">
        <span>Max payout {fmtDollars(pos.max_payout_cents)}</span>
        <span className="text-pos tabular">
          +{fmtDollars(pos.max_profit_cents)} potential
        </span>
      </div>
    </Card>
  );
}

function ProbBar({
  estimate,
  entry,
  side,
}: {
  estimate: number;
  entry: number;
  side: "yes" | "no";
}) {
  // For NO bets, the YES price implies (100 - estimate) and entry stays as-is
  // We show two markers on a 0-100 scale: market entry vs claudshi's estimate.
  const isYes = side === "yes";
  const market = isYes ? entry : 100 - entry;
  const est = estimate;
  return (
    <div className="flex-1">
      <div className="relative h-1.5 rounded-full bg-line">
        <motion.div
          className="absolute top-0 bottom-0 left-0 rounded-full bg-accent/60"
          initial={{ width: 0 }}
          animate={{ width: `${est}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        />
        <div
          className="absolute -top-1 w-px h-3.5 bg-ink-muted"
          style={{ left: `${market}%` }}
          title={`Market: ${market}¢`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-ink-dim mt-1 tabular">
        <span>est {est}%</span>
        <span>market {market}¢</span>
      </div>
    </div>
  );
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-baseline justify-between mb-4">
      <h2 className="text-sm font-medium text-ink-muted">
        {title}
        {count !== undefined && (
          <span className="ml-2 text-ink-dim tabular">{count}</span>
        )}
      </h2>
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Card className="p-12 text-center text-sm text-ink-muted">{children}</Card>
  );
}

function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-48 rounded-xl bg-bg-card" />
      <div className="grid grid-cols-2 gap-3">
        <div className="h-32 rounded-xl bg-bg-card" />
        <div className="h-32 rounded-xl bg-bg-card" />
      </div>
    </div>
  );
}
