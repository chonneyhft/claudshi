"""Tier 4: DecisionLogger — JSONL transcript correctness."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.logger import DecisionLogger


def _read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text().strip().split("\n") if line]


def test_session_id_is_8_chars(tmp_path):
    log = DecisionLogger(log_dir=str(tmp_path))
    assert len(log.session_id) == 8


def test_log_turn_writes_entry_to_jsonl(tmp_path):
    log = DecisionLogger(log_dir=str(tmp_path))
    log.log_turn(turn_number=1, role="assistant", content_text="hello")

    entries = _read_jsonl(log.log_file)
    assert len(entries) == 1
    assert entries[0]["role"] == "assistant"
    assert entries[0]["content_text"] == "hello"
    assert entries[0]["turn"] == 1


def test_content_text_is_truncated_at_2000_chars(tmp_path):
    log = DecisionLogger(log_dir=str(tmp_path))
    log.log_turn(turn_number=1, role="assistant", content_text="x" * 5000)
    entry = _read_jsonl(log.log_file)[0]
    assert len(entry["content_text"]) == 2000


def test_log_turn_with_tool_calls(tmp_path):
    log = DecisionLogger(log_dir=str(tmp_path))
    log.log_turn(
        turn_number=2, role="assistant",
        tool_calls=[{"id": "x", "name": "place_trade", "input": {"ticker": "KX1"}}],
    )
    entry = _read_jsonl(log.log_file)[0]
    assert entry["tool_calls"][0]["name"] == "place_trade"


def test_log_session_summary_appends(tmp_path):
    log = DecisionLogger(log_dir=str(tmp_path))
    log.log_turn(turn_number=1, role="assistant", content_text="x")
    log.log_session_summary(trades_made=2, portfolio_value_cents=12345, total_tokens=100)

    entries = _read_jsonl(log.log_file)
    assert len(entries) == 2
    summary = entries[-1]
    assert summary["type"] == "session_summary"
    assert summary["trades_made"] == 2
    assert summary["portfolio_value_dollars"] == "$123.45"


def test_read_logs_returns_recent_entries(tmp_path):
    # Write two sessions
    log1 = DecisionLogger(log_dir=str(tmp_path))
    log1.log_turn(turn_number=1, role="assistant", content_text="first")
    log2 = DecisionLogger(log_dir=str(tmp_path))
    log2.log_turn(turn_number=1, role="assistant", content_text="second")

    entries = DecisionLogger.read_logs(log_dir=str(tmp_path))
    assert len(entries) == 2
    contents = {e["content_text"] for e in entries}
    assert contents == {"first", "second"}


def test_read_logs_empty_dir_returns_empty_list(tmp_path):
    assert DecisionLogger.read_logs(log_dir=str(tmp_path / "missing")) == []


def test_read_logs_respects_last_n_files(tmp_path):
    for _ in range(5):
        log = DecisionLogger(log_dir=str(tmp_path))
        log.log_turn(turn_number=1, role="assistant", content_text="x")
    entries = DecisionLogger.read_logs(log_dir=str(tmp_path), last_n_files=2)
    assert len(entries) == 2
