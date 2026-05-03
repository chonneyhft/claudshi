from pathlib import Path

import config

JOURNAL_PATH = Path(config.BASE_DIR) / "data" / "journal.md"
MAX_JOURNAL_CHARS = 3000


def read_journal() -> str:
    if not JOURNAL_PATH.exists():
        return ""
    text = JOURNAL_PATH.read_text().strip()
    if len(text) > MAX_JOURNAL_CHARS:
        text = text[:MAX_JOURNAL_CHARS] + "\n...[truncated]"
    return text


def write_journal(content: str):
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if len(content) > MAX_JOURNAL_CHARS:
        content = content[:MAX_JOURNAL_CHARS]
    JOURNAL_PATH.write_text(content)
