"""Tier 4: journal — read/write with size cap."""
from __future__ import annotations

import pytest

from agent import journal


@pytest.fixture
def patched_journal(tmp_path, monkeypatch):
    path = tmp_path / "journal.md"
    monkeypatch.setattr(journal, "JOURNAL_PATH", path)
    return path


def test_read_empty_when_file_missing(patched_journal):
    assert journal.read_journal() == ""


def test_write_then_read_round_trip(patched_journal):
    journal.write_journal("hello world")
    assert journal.read_journal() == "hello world"


def test_write_truncates_to_max_chars(patched_journal):
    long_content = "x" * (journal.MAX_JOURNAL_CHARS + 500)
    journal.write_journal(long_content)
    written = patched_journal.read_text()
    assert len(written) == journal.MAX_JOURNAL_CHARS


def test_read_truncates_oversized_file(patched_journal):
    """Even if the file was written by some other process, read caps the size."""
    patched_journal.parent.mkdir(parents=True, exist_ok=True)
    patched_journal.write_text("x" * (journal.MAX_JOURNAL_CHARS + 100))
    text = journal.read_journal()
    assert text.endswith("...[truncated]")


def test_write_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "a" / "b" / "journal.md"
    monkeypatch.setattr(journal, "JOURNAL_PATH", nested)
    journal.write_journal("hi")
    assert nested.read_text() == "hi"
