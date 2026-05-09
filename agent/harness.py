import time

import anthropic

import config
from agent.logger import DecisionLogger
from agent.prompts import build_system_prompt
from agent.tools import ToolDispatcher, get_tools
from engine.paper_trader import PaperTrader

MAX_TOOL_RESULT_CHARS = 4000
MAX_CONSECUTIVE_ERRORS = 3
SESSION_TIMEOUT_SECONDS = 600
MAX_API_RETRIES = 4
RETRY_BACKOFF_BASE_SECONDS = 1.0


def _is_transient(exc: anthropic.APIError) -> bool:
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    status = getattr(exc, "status_code", None)
    return status in (408, 409, 429, 500, 502, 503, 504, 529)


class AgentHarness:
    def __init__(
        self,
        paper_trader: PaperTrader,
        tool_dispatcher: ToolDispatcher,
        decision_logger: DecisionLogger,
    ):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.trader = paper_trader
        self.dispatcher = tool_dispatcher
        self.logger = decision_logger
        self.model = config.CLAUDE_MODEL
        self.max_turns = config.MAX_AGENT_TURNS

    def run_session(
        self, user_message: str = "Analyze the markets and make trading decisions."
    ) -> dict:
        portfolio = self.trader.get_portfolio()

        from agent.market_feed import build_market_feed
        held_tickers = [p.ticker for p in portfolio.positions]
        market_feed = build_market_feed(self.dispatcher.kalshi, held_tickers)

        system = build_system_prompt(
            balance_cents=portfolio.balance_cents,
            num_positions=len(portfolio.positions),
            realized_pnl_cents=portfolio.realized_pnl_cents,
            db=self.trader.db,
            market_feed=market_feed,
        )

        tools = get_tools()
        messages = [{"role": "user", "content": user_message}]
        turn = 0
        total_input_tokens = 0
        total_output_tokens = 0
        trades_made = 0
        consecutive_errors = 0
        final_text = ""
        session_start = time.time()

        while turn < self.max_turns:
            if time.time() - session_start > SESSION_TIMEOUT_SECONDS:
                final_text = "[Session timed out]"
                break

            turn += 1
            response = None
            last_error: anthropic.APIError | None = None
            for attempt in range(MAX_API_RETRIES + 1):
                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        system=system,
                        tools=tools,
                        messages=messages,
                    )
                    break
                except anthropic.APIError as e:
                    last_error = e
                    if attempt >= MAX_API_RETRIES or not _is_transient(e):
                        break
                    delay = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                    self.logger.log_turn(
                        turn_number=turn,
                        role="warning",
                        content_text=f"Transient API error (attempt {attempt + 1}): {e}; retrying in {delay:.1f}s",
                    )
                    time.sleep(delay)

            if response is None:
                self.logger.log_turn(
                    turn_number=turn,
                    role="error",
                    content_text=f"API error: {last_error}",
                )
                final_text = f"[API error: {last_error}]"
                break

            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens": getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": getattr(
                    response.usage, "cache_read_input_tokens", 0
                ),
            }
            total_input_tokens += usage["input_tokens"]
            total_output_tokens += usage["output_tokens"]

            text_parts = []
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(
                        {"id": block.id, "name": block.name, "input": block.input}
                    )

            self.logger.log_turn(
                turn_number=turn,
                role="assistant",
                content_text="\n".join(text_parts),
                tool_calls=tool_calls if tool_calls else None,
                token_usage=usage,
            )

            if response.stop_reason == "end_turn":
                final_text = "\n".join(text_parts)
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results_content = []
                tool_results_log = []
                turn_had_error = False
                for tc in tool_calls:
                    result_str, raw = self.dispatcher.dispatch(tc["name"], tc["input"])

                    if len(result_str) > MAX_TOOL_RESULT_CHARS:
                        result_str = result_str[:MAX_TOOL_RESULT_CHARS] + "...[truncated]"

                    is_error = isinstance(raw, dict) and "error" in raw
                    is_filled_trade = (
                        tc["name"] == "place_trade"
                        and isinstance(raw, dict)
                        and raw.get("status") == "filled"
                    )

                    tool_results_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": result_str,
                            **({"is_error": True} if is_error else {}),
                        }
                    )
                    tool_results_log.append(
                        {
                            "tool_name": tc["name"],
                            "input": tc["input"],
                            "result": result_str[:500],
                        }
                    )
                    if is_filled_trade:
                        trades_made += 1
                    if is_error:
                        turn_had_error = True

                if turn_had_error:
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS and tool_results_content:
                    last = tool_results_content[-1]
                    last["content"] = (
                        last["content"]
                        + "\n\n[System: multiple consecutive tool errors. "
                        "Please try a different approach or wrap up your analysis.]"
                    )
                    consecutive_errors = 0

                self.logger.log_turn(
                    turn_number=turn,
                    role="tool_results",
                    tool_results=tool_results_log,
                )

                messages.append({"role": "user", "content": tool_results_content})
            else:
                final_text = "\n".join(text_parts)
                self.logger.log_turn(
                    turn_number=turn,
                    role="system",
                    content_text=f"[Session ended: stop_reason={response.stop_reason}]",
                )
                break

        portfolio = self.trader.get_portfolio()
        self.logger.log_session_summary(
            trades_made=trades_made,
            portfolio_value_cents=portfolio.total_value_cents,
            total_tokens=total_input_tokens + total_output_tokens,
        )

        return {
            "session_id": self.logger.session_id,
            "turns": turn,
            "trades_made": trades_made,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "portfolio_value": f"${portfolio.total_value_cents / 100:.2f}",
            "total_pnl": f"${portfolio.total_pnl_cents / 100:+.2f}",
            "final_response": final_text[:500],
        }
