import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "../components/Card";
import { Stat } from "../components/Stat";
import { usePortfolio, useSnapshots } from "../lib/api";
import { fmtDollars, fmtPct } from "../lib/format";

export function PnlView() {
  const { data: p } = usePortfolio();
  const { data: snaps } = useSnapshots();

  if (!p || !snaps) return <div className="text-ink-muted">Loading…</div>;

  if (snaps.length === 0) {
    return (
      <Card className="p-12 text-center text-sm text-ink-muted">
        No snapshots yet. Run a trading session to start tracking P&L.
      </Card>
    );
  }

  const chartData = snaps.map((s) => ({
    t: s.timestamp,
    label: new Date(s.timestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    total: s.total_value_cents / 100,
    cash: s.balance_cents / 100,
    positions: s.positions_value_cents / 100,
    realized: s.realized_pnl_cents / 100,
    unrealized: s.unrealized_pnl_cents / 100,
  }));

  const positive = p.pct_return >= 0;

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <Stat
          label="Starting"
          value={fmtDollars(p.starting_balance.cents)}
        />
        <Stat
          label="Current"
          value={fmtDollars(p.total_value.cents)}
          sub={fmtPct(p.pct_return)}
          tone={positive ? "pos" : "neg"}
        />
        <Stat
          label="Realized"
          value={fmtDollars(p.realized_pnl.cents, { sign: true })}
          tone={p.realized_pnl.cents >= 0 ? "pos" : "neg"}
        />
        <Stat
          label="Unrealized"
          value={fmtDollars(p.unrealized_pnl.cents, { sign: true })}
          tone={p.unrealized_pnl.cents >= 0 ? "pos" : "neg"}
        />
      </section>

      <Card className="p-6">
        <h3 className="text-sm font-medium text-ink-muted mb-4">
          Portfolio value
        </h3>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="total-grad" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={positive ? "#3ecf8e" : "#f87171"}
                  stopOpacity={0.25}
                />
                <stop
                  offset="100%"
                  stopColor={positive ? "#3ecf8e" : "#f87171"}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v.toLocaleString()}`}
              width={70}
              domain={["dataMin - 50", "dataMax + 50"]}
            />
            <Tooltip content={<ChartTooltip />} />
            <Area
              type="monotone"
              dataKey="total"
              stroke={positive ? "#3ecf8e" : "#f87171"}
              strokeWidth={2}
              fill="url(#total-grad)"
              isAnimationActive
              animationDuration={900}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-6">
          <h3 className="text-sm font-medium text-ink-muted mb-4">
            Cash vs positions
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                minTickGap={40}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${v.toLocaleString()}`}
                width={70}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="cash"
                stackId="1"
                stroke="#6366f1"
                fill="#6366f1"
                fillOpacity={0.4}
                strokeWidth={1.5}
                isAnimationActive
              />
              <Area
                type="monotone"
                dataKey="positions"
                stackId="1"
                stroke="#f59e0b"
                fill="#f59e0b"
                fillOpacity={0.4}
                strokeWidth={1.5}
                isAnimationActive
              />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-6">
          <h3 className="text-sm font-medium text-ink-muted mb-4">
            P&L breakdown
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                minTickGap={40}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${v.toLocaleString()}`}
                width={70}
              />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="realized"
                stroke="#3ecf8e"
                strokeWidth={1.8}
                dot={false}
                isAnimationActive
              />
              <Line
                type="monotone"
                dataKey="unrealized"
                stroke="#f59e0b"
                strokeWidth={1.8}
                strokeDasharray="3 3"
                dot={false}
                isAnimationActive
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-3 text-xs text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-px bg-pos" /> realized
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-px bg-[#f59e0b] border-dashed" /> unrealized
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-bg-card px-3 py-2 text-xs shadow-xl">
      <div className="text-ink-dim mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-3 tabular">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: p.color }}
          />
          <span className="text-ink-muted capitalize w-20">{p.dataKey}</span>
          <span className="text-ink">
            $
            {p.value.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      ))}
    </div>
  );
}
