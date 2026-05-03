import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config


class DecisionLogger:
    def __init__(self, log_dir: str = config.LOG_DIR):
        self.session_id = str(uuid.uuid4())[:8]
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.log_file = log_path / f"{ts}_{self.session_id}.jsonl"
        self._turns: List[dict] = []

    def log_turn(
        self,
        turn_number: int,
        role: str,
        content_text: str = "",
        tool_calls: Optional[List[dict]] = None,
        tool_results: Optional[List[dict]] = None,
        token_usage: Optional[dict] = None,
    ):
        entry = {
            "session_id": self.session_id,
            "turn": turn_number,
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content_text": content_text[:2000] if content_text else "",
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "token_usage": token_usage,
        }
        self._turns.append(entry)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log_session_summary(
        self, trades_made: int, portfolio_value_cents: int, total_tokens: int
    ):
        summary = {
            "session_id": self.session_id,
            "type": "session_summary",
            "timestamp": datetime.now().isoformat(),
            "trades_made": trades_made,
            "portfolio_value_dollars": f"${portfolio_value_cents / 100:.2f}",
            "total_turns": len(self._turns),
            "total_tokens": total_tokens,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(summary, default=str) + "\n")

    @staticmethod
    def read_logs(log_dir: str = config.LOG_DIR, last_n_files: int = 10) -> List[dict]:
        log_path = Path(log_dir)
        if not log_path.exists():
            return []
        files = sorted(log_path.glob("*.jsonl"), reverse=True)[:last_n_files]
        entries = []
        for f in files:
            for line in f.read_text().strip().split("\n"):
                if line:
                    entries.append(json.loads(line))
        return entries
