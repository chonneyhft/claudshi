import useSWR from "swr";

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  });

export type Money = { cents: number; dollars: number };

export type Portfolio = {
  starting_balance: Money;
  balance: Money;
  positions_value: Money;
  total_value: Money;
  cost_basis: Money;
  realized_pnl: Money;
  unrealized_pnl: Money;
  total_pnl: Money;
  pct_return: number;
  num_positions: number;
  num_trades: number;
  model: string;
  interval_hours: number;
  research_enabled: boolean;
};

export type ThesisLite = {
  id: string;
  probability_estimate: number;
  market_price_at_entry: number;
  entry_thesis: string;
  edge_cents: number;
  category: string;
};

export type Position = {
  ticker: string;
  side: "yes" | "no";
  quantity: number;
  avg_price_cents: number;
  cost_basis_cents: number;
  max_payout_cents: number;
  max_profit_cents: number;
  opened_at: string;
  thesis: ThesisLite | null;
};

export type Trade = {
  id: string;
  ticker: string;
  market_title: string;
  side: "yes" | "no";
  action: "buy" | "sell" | "settle";
  quantity: number;
  price_cents: number;
  total_cost_cents: number;
  reasoning: string;
  session_id: string;
  thesis_id: string;
  timestamp: string;
};

export type Snapshot = {
  timestamp: string;
  balance_cents: number;
  positions_value_cents: number;
  total_value_cents: number;
  realized_pnl_cents: number;
  unrealized_pnl_cents: number;
  num_positions: number;
};

export type SessionSummary = {
  session_id: string;
  timestamp: string;
  turns: number;
  tool_calls: number;
  trades_made: number;
  portfolio_value: string | null;
  input_tokens: number;
  output_tokens: number;
  est_cost_dollars: number;
};

export type Thesis = {
  id: string;
  ticker: string;
  side_predicted: "yes" | "no";
  category: string;
  entry_thesis: string;
  probability_estimate: number;
  market_price_at_entry: number;
  edge_cents: number;
  status: "active" | "closed" | "settled";
  exit_thesis: string;
  outcome: "win" | "loss" | "partial" | "";
  realized_pnl_cents: number;
  created_at: string;
  closed_at: string | null;
  session_id: string;
};

export type SessionDetail = {
  session_id: string;
  entries: SessionEntry[];
};

export type SessionEntry = {
  type?: string;
  role?: string;
  turn?: number;
  timestamp?: string;
  session_id?: string;
  content_text?: string;
  tool_calls?: { name: string; input: Record<string, unknown> }[];
  tool_results?: { tool_name: string; result: string }[];
  token_usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  };
  trades_made?: number;
  portfolio_value_dollars?: string;
};

const swrOpts = { refreshInterval: 30_000, revalidateOnFocus: true };

export const usePortfolio = () =>
  useSWR<Portfolio>("/api/portfolio", fetcher, swrOpts);
export const usePositions = () =>
  useSWR<Position[]>("/api/positions", fetcher, swrOpts);
export const useTrades = () =>
  useSWR<Trade[]>("/api/trades", fetcher, swrOpts);
export const useSnapshots = () =>
  useSWR<Snapshot[]>("/api/snapshots", fetcher, swrOpts);
export const useSessions = () =>
  useSWR<SessionSummary[]>("/api/sessions", fetcher, swrOpts);
export const useSession = (id: string | null) =>
  useSWR<SessionDetail>(id ? `/api/sessions/${id}` : null, fetcher);
export const useTheses = () =>
  useSWR<Thesis[]>("/api/theses", fetcher, swrOpts);
