"""
Subprocess-based Python sandbox for the agent's read-side operations.

Exposes `kalshi` (KalshiDataClient) and `trader` (PaperTrader) to agent-written
code. Only print() output flows back into context.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

SANDBOX_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 4000

# The runner script template — executed in a subprocess
_RUNNER_TEMPLATE = '''
import sys
import json

sys.path.insert(0, {project_root!r})

import config
from kalshi.client import KalshiDataClient
from engine.db import Database
from engine.paper_trader import PaperTrader

# Initialize clients (read-only usage)
kalshi = KalshiDataClient()
_db = Database(config.DB_PATH)
_db.seed_portfolio(config.STARTING_BALANCE_CENTS)
trader = PaperTrader(_db, kalshi)

# --- User code below ---
{user_code}
'''


def run_python(code: str) -> str:
    project_root = str(Path(__file__).parent.parent)

    runner = _RUNNER_TEMPLATE.format(
        project_root=project_root,
        user_code=textwrap.dedent(code),
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", runner],
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT_SECONDS,
            cwd=project_root,
        )
    except subprocess.TimeoutExpired:
        return "[Error: Code execution timed out (30s limit)]"

    output = result.stdout
    if result.returncode != 0:
        stderr = result.stderr
        # Extract the useful part of the traceback
        if "Traceback" in stderr:
            lines = stderr.strip().split("\n")
            # Find where user code traceback starts
            relevant = []
            in_traceback = False
            for line in lines:
                if line.startswith("Traceback"):
                    in_traceback = True
                if in_traceback:
                    relevant.append(line)
            error_msg = "\n".join(relevant[-10:])
        else:
            error_msg = stderr[-500:] if stderr else "Unknown error"
        output = output + f"\n[Error]\n{error_msg}" if output else f"[Error]\n{error_msg}"

    if not output.strip():
        return "[No output — use print() to see results]"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"

    return output
