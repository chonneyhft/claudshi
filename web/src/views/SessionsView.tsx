import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { useSession, useSessions, type SessionEntry } from "../lib/api";
import { fmtDate } from "../lib/format";

export function SessionsView() {
  const { data: sessions } = useSessions();
  const [openId, setOpenId] = useState<string | null>(null);

  if (!sessions) return <div className="text-ink-muted">Loading…</div>;

  return (
    <div className="space-y-4">
      <div className="text-xs text-ink-dim">{sessions.length} sessions</div>
      <div className="space-y-2">
        {sessions.map((s, i) => {
          const open = openId === s.session_id;
          return (
            <Card key={s.session_id} delay={i * 0.03} className="overflow-hidden">
              <button
                onClick={() => setOpenId(open ? null : s.session_id)}
                className="w-full px-5 py-4 flex items-center gap-4 text-left hover:bg-bg-subtle/40 transition-colors"
              >
                <div className="font-mono text-xs text-ink-muted w-20">
                  {s.session_id.slice(0, 8)}
                </div>
                <div className="text-sm text-ink-muted w-32">
                  {s.timestamp ? fmtDate(s.timestamp) : "—"}
                </div>
                <div className="flex items-center gap-2 flex-1">
                  <MetricChip label="turns" value={s.turns} />
                  <MetricChip label="tools" value={s.tool_calls} />
                  <MetricChip
                    label="trades"
                    value={s.trades_made}
                    accent={s.trades_made > 0}
                  />
                  <MetricChip
                    label="tokens"
                    value={`${((s.input_tokens + s.output_tokens) / 1000).toFixed(1)}k`}
                  />
                  <MetricChip
                    label="cost"
                    value={`$${s.est_cost_dollars.toFixed(2)}`}
                  />
                </div>
                {s.portfolio_value && (
                  <div className="tabular text-sm text-ink-muted">
                    {s.portfolio_value}
                  </div>
                )}
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
                {open && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden border-t border-line/60"
                  >
                    <SessionDetail sessionId={s.session_id} />
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function MetricChip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-1.5 text-xs">
      <span className="text-ink-dim uppercase tracking-wider">{label}</span>
      <span
        className={
          "tabular font-medium " + (accent ? "text-pos" : "text-ink-muted")
        }
      >
        {value}
      </span>
    </div>
  );
}

function SessionDetail({ sessionId }: { sessionId: string }) {
  const { data } = useSession(sessionId);
  if (!data) {
    return (
      <div className="px-5 py-6 text-sm text-ink-dim">Loading session…</div>
    );
  }

  const entries = data.entries.filter((e) => e.type !== "session_summary");

  return (
    <div className="px-5 py-5 space-y-4 bg-bg-subtle/30">
      {entries.map((e, i) => (
        <EntryView entry={e} key={i} />
      ))}
    </div>
  );
}

function EntryView({ entry }: { entry: SessionEntry }) {
  if (entry.role === "assistant") {
    return (
      <div className="space-y-2">
        {entry.content_text && (
          <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
            <span className="text-ink-dim text-xs uppercase tracking-wider mr-2">
              turn {entry.turn}
            </span>
            {entry.content_text}
          </div>
        )}
        {entry.tool_calls && entry.tool_calls.length > 0 && (
          <div className="flex flex-wrap gap-1.5 ml-1">
            {entry.tool_calls.map((tc, i) => (
              <code
                key={i}
                className="text-[11px] px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20 font-mono"
              >
                {tc.name}
              </code>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (entry.role === "tool_results" && entry.tool_results) {
    return (
      <div className="space-y-1 pl-4 border-l border-line/60">
        {entry.tool_results.map((tr, i) => {
          const isErr = tr.result.toLowerCase().includes("error");
          const isTrade = tr.tool_name === "place_trade";
          return (
            <div
              key={i}
              className={
                "text-xs flex gap-2 " +
                (isErr
                  ? "text-neg"
                  : isTrade
                    ? "text-pos"
                    : "text-ink-dim")
              }
            >
              <Pill tone={isErr ? "neg" : isTrade ? "pos" : "muted"}>
                {tr.tool_name}
              </Pill>
              <span className="font-mono truncate flex-1">
                {tr.result.slice(0, 200)}
              </span>
            </div>
          );
        })}
      </div>
    );
  }
  if (entry.role === "error") {
    return (
      <div className="text-sm text-neg">⚠ {entry.content_text}</div>
    );
  }
  return null;
}
